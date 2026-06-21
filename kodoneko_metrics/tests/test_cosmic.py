"""
Tests pour le module kodoneko_metrics.cosmic.

Couvre les détecteurs Python (Django, Flask, FastAPI, SQLAlchemy, Redis,
pymongo, raw SQL, file I/O, HTTP clients, Celery, Click) et les
agrégations (CosmicFileReport, CosmicScanReport, CosmicDelta).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pytest

from kodoneko_metrics.cosmic import (
    CosmicAnalyzer,
    CosmicDelta,
    CosmicFileReport,
    CosmicMovement,
    CosmicScanReport,
    MOVEMENT_TYPES,
)


# ===========================================================================
# Tests : détection Python — Web frameworks
# ===========================================================================

class TestPythonWebFrameworks:

    def test_flask_route_with_decorator(self):
        src = b"""
from flask import Flask, jsonify
app = Flask(__name__)

@app.route("/health")
def health():
    return jsonify({"ok": True})
"""
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python", "app.py")
        assert r.total_cfp == 2  # 1 entry + 1 exit
        assert r.by_type["entry"] == 1
        assert r.by_type["exit"] == 1
        assert r.by_framework.get("flask", 0) >= 1

    def test_fastapi_async_route(self):
        src = b"""
from fastapi import FastAPI
api = FastAPI()

@api.get("/users")
async def list_users():
    return []
"""
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python", "main.py")
        assert r.by_type["entry"] == 1
        assert r.by_type["exit"] == 1
        # Le framework détecté doit être fastapi (route async)
        assert "fastapi" in r.by_framework

    def test_django_view_function(self):
        src = b"""
from django.http import JsonResponse

def get_user(request, user_id):
    return JsonResponse({"id": user_id})
"""
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python", "views.py")
        assert r.by_type["entry"] == 1
        assert r.by_type["exit"] == 1
        assert "django" in r.by_framework

    def test_decorator_call_not_counted_as_call(self):
        """@api.get("/users") ne doit pas être compté comme un HTTP client call."""
        src = b"""
from fastapi import FastAPI
api = FastAPI()

@api.get("/users")
async def list_users():
    return []
"""
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python", "main.py")
        # Il ne doit y avoir aucun http_client_get
        for m in r.movements:
            assert "http_client" not in m.detector, \
                f"Faux positif HTTP client : {m.detector} L{m.line}"

    def test_web_implicit_return_as_exit(self):
        """Un `return` direct dans une route web doit compter comme Exit."""
        src = b"""
from fastapi import FastAPI
api = FastAPI()

@api.get("/users")
async def list_users():
    return [1, 2, 3]
"""
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python", "main.py")
        assert r.by_type["exit"] == 1


# ===========================================================================
# Tests : détection Python — ORM
# ===========================================================================

class TestPythonORM:

    def test_django_orm_get(self):
        src = b"User.objects.get(id=1)"
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        assert r.by_type["read"] == 1
        assert r.movements[0].detector == "django_orm_get"

    def test_django_orm_create_save(self):
        src = b"""
user = User.objects.create(name="bob")
user.save()
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        # 1 create + 1 save = 2 writes
        assert r.by_type["write"] == 2

    def test_django_orm_chain_deduplication(self):
        """User.objects.filter(...).first() doit compter 1 read, pas 2."""
        src = b"users = User.objects.filter(active=True).first()"
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        assert r.by_type["read"] == 1, \
            f"Chaîne filter().first() devrait compter 1 read, pas {r.by_type['read']}"

    def test_sqlalchemy_session_methods(self):
        src = b"""
user = session.scalar(select(User).where(User.id == 1))
session.add(other_user)
session.commit()
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        # D-PY8 : commit() n'est PAS un write distinct (acte transactionnel).
        # 1 read (scalar) + 1 write (add). commit() est ignoré.
        assert r.by_type["read"] == 1
        assert r.by_type["write"] == 1

    def test_pymongo_specific_methods(self):
        src = b"""
result = collection.find_one({"_id": 1})
collection.insert_one({"name": "test"})
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        assert r.by_type["read"] == 1
        assert r.by_type["write"] == 1

    def test_pymongo_ambiguous_find_requires_context(self):
        """text.find("{") ne doit PAS être compté comme pymongo.find()."""
        src = b'pos = text.find("{")'
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        # Aucun mouvement détecté
        for m in r.movements:
            assert "pymongo" not in m.detector, \
                f"Faux positif pymongo : {m.detector}"


# ===========================================================================
# Tests : détection Python — Redis
# ===========================================================================

class TestPythonRedis:

    def test_redis_get_with_context(self):
        src = b'cached = redis_client.get("user:1")'
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        assert r.by_type["read"] == 1
        assert r.movements[0].framework == "redis"

    def test_redis_setex(self):
        src = b'cache.setex("key", 60, "value")'
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        assert r.by_type["write"] == 1
        assert r.movements[0].framework == "redis"

    def test_redis_specific_methods_dont_need_context(self):
        """hgetall, zrange, smembers sont assez spécifiques à Redis."""
        src = b"""
data = obj.hgetall("key")
items = obj.zrange("scores", 0, -1)
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        # Les deux doivent être détectés malgré "obj" sans contexte évident
        redis_movements = [m for m in r.movements if m.framework == "redis"]
        assert len(redis_movements) == 2


# ===========================================================================
# Tests : détection Python — Raw SQL
# ===========================================================================

class TestPythonRawSQL:

    def test_raw_sql_select(self):
        src = b'cursor.execute("SELECT * FROM users")'
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        assert r.by_type["read"] == 1
        assert r.movements[0].detector == "raw_sql_select"

    def test_raw_sql_insert(self):
        src = b'cursor.execute("INSERT INTO users VALUES (%s)", (name,))'
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        assert r.by_type["write"] == 1

    def test_raw_sql_update_delete(self):
        src = b"""
cursor.execute("UPDATE users SET active = 0")
cursor.execute("DELETE FROM users WHERE id = 1")
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        assert r.by_type["write"] == 2


# ===========================================================================
# Tests : détection Python — File I/O
# ===========================================================================

class TestPythonFileIO:

    def test_open_read_default_mode(self):
        src = b'with open("data.txt") as f: pass'
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        assert r.by_type["read"] == 1

    def test_open_write_mode(self):
        src = b'with open("data.txt", "w") as f: pass'
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        assert r.by_type["write"] == 1

    def test_pathlib_read_write(self):
        src = b"""
content = path.read_text()
path.write_text("new")
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        assert r.by_type["read"] == 1
        assert r.by_type["write"] == 1


# ===========================================================================
# Tests : détection Python — HTTP client
# ===========================================================================

class TestPythonHTTPClient:

    def test_requests_get_in_practical_mode(self):
        src = b'response = requests.get("https://example.com")'
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python")
        # 1 write (req) + 1 read (resp)
        assert r.by_type["write"] == 1
        assert r.by_type["read"] == 1

    def test_http_client_not_counted_in_strict_mode(self):
        src = b'response = requests.get("https://example.com")'
        a = CosmicAnalyzer(mode="strict")
        r = a.analyze_source(src, "python")
        assert r.total_cfp == 0

    def test_redis_client_get_not_detected_as_http(self):
        """redis_client.get(...) ne doit PAS être détecté comme HTTP."""
        src = b'value = redis_client.get("key")'
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python")
        for m in r.movements:
            assert "http_client" not in m.detector, \
                f"Faux positif HTTP : {m.detector}"


# ===========================================================================
# Tests : détection Python — Celery & Click
# ===========================================================================

class TestPythonCeleryClick:

    def test_celery_task_decorator(self):
        src = b"""
from celery import Celery
app = Celery("tasks")

@app.task
def send_email(user_id):
    pass
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        celery = [m for m in r.movements if m.framework == "celery"]
        assert len(celery) == 1
        assert celery[0].type == "entry"

    def test_click_command_decorator(self):
        src = b"""
import click

@click.command
def hello():
    click.echo("hi")
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        click_mvts = [m for m in r.movements if m.framework == "click"]
        assert len(click_mvts) == 1
        assert click_mvts[0].type == "entry"


# ===========================================================================
# Tests : modèles d'agrégation
# ===========================================================================

class TestModels:

    def test_cosmic_movement_to_dict(self):
        m = CosmicMovement(
            type="read", file="x.py", line=10,
            code_excerpt="User.objects.get(id=1)",
            detector="django_orm_get", framework="django",
        )
        d = m.to_dict()
        assert d["type"] == "read"
        assert d["line"] == 10
        assert d["framework"] == "django"

    def test_cosmic_file_report_aggregations(self):
        fr = CosmicFileReport(path="x.py", language="python")
        fr.movements.append(CosmicMovement(
            type="read", file="x.py", line=1, code_excerpt="",
            detector="d1", framework="django",
        ))
        fr.movements.append(CosmicMovement(
            type="write", file="x.py", line=2, code_excerpt="",
            detector="d2", framework="redis",
        ))
        assert fr.total_cfp == 2
        assert fr.by_type["read"] == 1
        assert fr.by_type["write"] == 1
        assert fr.by_framework == {"django": 1, "redis": 1}

    def test_cosmic_scan_report_aggregation(self):
        fr1 = CosmicFileReport(path="a.py", language="python")
        fr1.movements.append(CosmicMovement(
            type="read", file="a.py", line=1, code_excerpt="",
            detector="d", framework="django",
        ))
        fr2 = CosmicFileReport(path="b.py", language="python")
        fr2.movements.append(CosmicMovement(
            type="write", file="b.py", line=1, code_excerpt="",
            detector="d", framework="django",
        ))
        fr2.movements.append(CosmicMovement(
            type="write", file="b.py", line=2, code_excerpt="",
            detector="d", framework="redis",
        ))
        report = CosmicScanReport(scope="test", mode="practical")
        report.files = [fr1, fr2]
        assert report.total_cfp == 3
        assert report.by_type["read"] == 1
        assert report.by_type["write"] == 2
        assert report.by_framework == {"django": 2, "redis": 1}
        # Top files
        top = report.top_files(1)
        assert len(top) == 1
        assert top[0].path == "b.py"  # 2 CFP > 1 CFP

    def test_cosmic_delta(self):
        before = CosmicScanReport(scope="before", mode="practical")
        before.files.append(CosmicFileReport(path="a.py", language="python"))
        before.files[0].movements.append(CosmicMovement(
            type="read", file="a.py", line=1, code_excerpt="",
            detector="d", framework="django",
        ))

        after = CosmicScanReport(scope="after", mode="practical")
        after.files.append(CosmicFileReport(path="a.py", language="python"))
        after.files[0].movements.extend([
            CosmicMovement(type="read", file="a.py", line=1, code_excerpt="",
                            detector="d", framework="django"),
            CosmicMovement(type="write", file="a.py", line=2, code_excerpt="",
                            detector="d", framework="django"),
        ])

        delta = CosmicDelta(scope="commit:abc", mode="practical",
                             before=before, after=after)
        assert delta.cfp_added == 1
        assert delta.by_type_delta["write"] == 1
        assert delta.by_type_delta["read"] == 0


# ===========================================================================
# Tests : modes strict vs practical
# ===========================================================================

class TestModes:

    def test_practical_counts_http_clients(self):
        src = b'r = requests.get("https://x.com")'
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python")
        assert r.total_cfp == 2  # write + read

    def test_strict_skips_http_clients(self):
        src = b'r = requests.get("https://x.com")'
        a = CosmicAnalyzer(mode="strict")
        r = a.analyze_source(src, "python")
        assert r.total_cfp == 0


# ===========================================================================
# Tests : gestion d'erreurs
# ===========================================================================

class TestErrorHandling:

    def test_unsupported_language(self):
        a = CosmicAnalyzer()
        r = a.analyze_source(b"const x = 1;", "javascript")
        # JavaScript pas encore implémenté → rapport vide
        assert r.total_cfp == 0

    def test_syntax_error_python(self):
        src = b"def broken(:"
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "python")
        # SyntaxError → rapport vide, pas d'exception
        assert r.total_cfp == 0

    def test_empty_source(self):
        a = CosmicAnalyzer()
        r = a.analyze_source(b"", "python")
        assert r.total_cfp == 0


# ===========================================================================
# Test d'intégration : scan d'un fichier multi-frameworks
# ===========================================================================

class TestIntegration:

    def test_full_backend_example(self):
        src = b"""
from fastapi import FastAPI
import redis, requests

api = FastAPI()
cache = redis.Redis()

@api.get("/users/{uid}")
async def get_user(uid: int):
    cached = cache.get(f"user:{uid}")
    if cached:
        return cached
    user = session.scalar(select(User).where(User.id == uid))
    cache.setex(f"user:{uid}", 60, user.to_json())
    return user.to_dict()

@api.post("/users")
async def create_user(payload: dict):
    user = User(**payload)
    session.add(user)
    session.commit()
    requests.post("https://api.email.com/welcome", json={"id": user.id})
    return {"id": user.id}
"""
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python", "backend.py")
        # Vérifications globales
        assert r.by_type["entry"] == 2  # 2 endpoints
        assert r.by_type["exit"] == 3   # 3 returns dans 2 endpoints
        assert r.by_type["read"] >= 2   # cache.get + session.scalar + HTTP resp
        assert r.by_type["write"] >= 3  # cache.setex + session.add/commit + HTTP req
        # Frameworks attendus
        assert "fastapi" in r.by_framework
        assert "redis" in r.by_framework
        assert "sqlalchemy" in r.by_framework
        assert "http_client" in r.by_framework


# ===========================================================================
# D-PY10 : Error messages HTTP (raise HTTPException, abort)
# ===========================================================================

class TestPythonHTTPErrors:

    def test_raise_httpexception_in_fastapi_endpoint_counts_as_exit(self):
        """D-PY10 : raise HTTPException dans un endpoint → 1 Exit error."""
        src = b'''
from fastapi import FastAPI, HTTPException
app = FastAPI()

@app.get("/item/{id}")
def get_item(id: int):
    if id < 0:
        raise HTTPException(404, "not found")
    return {"id": id}
'''
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python")
        assert r.by_type["entry"] == 1
        # 1 exit raise + 1 exit return
        assert r.by_type["exit"] == 2

    def test_multiple_raises_same_endpoint_one_exit(self):
        """D-PY10 frequency rule : N raises dans même endpoint = 1 Exit error."""
        src = b'''
from fastapi import FastAPI, HTTPException
app = FastAPI()

@app.get("/item/{id}")
def get_item(id: int):
    if id < 0:
        raise HTTPException(400, "bad id")
    if id > 1000:
        raise HTTPException(404, "not found")
    if id == 666:
        raise HTTPException(403, "forbidden")
    return {"id": id}
'''
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python")
        # Malgré 3 raises HTTPException → 1 SEUL Exit error (frequency rule)
        # + 1 return implicit
        assert r.by_type["exit"] == 2

    def test_raise_outside_endpoint_ignored(self):
        """D-PY10 garde-fou : raise hors contexte endpoint = pas d'Exit."""
        src = b'''
from fastapi import HTTPException

def validate_id(id):
    """Utility function, NOT an endpoint."""
    if id < 0:
        raise HTTPException(400, "bad id")
    return id
'''
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python")
        # validate_id n'est pas un endpoint → raise ignoré
        assert r.by_type["exit"] == 0

    def test_raise_valueerror_not_counted(self):
        """D-PY10 : seules les exceptions HTTP whitelist sont comptées."""
        src = b'''
from fastapi import FastAPI
app = FastAPI()

@app.get("/item/{id}")
def get_item(id: int):
    if id < 0:
        raise ValueError("bad id")  # ValueError = pas HTTP
    return {"id": id}
'''
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python")
        # Seul le return compte (ValueError pas dans whitelist)
        assert r.by_type["exit"] == 1

    def test_flask_abort_counted_as_exit(self):
        """D-PY10 : abort() Flask → 1 Exit error (équivalent raise)."""
        src = b'''
from flask import Flask, abort, jsonify
app = Flask(__name__)

@app.route("/item/<int:id>")
def get_item(id):
    if id < 0:
        abort(400, "bad id")
    return jsonify({"id": id})
'''
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python")
        # abort + jsonify = 2 exits
        assert r.by_type["exit"] == 2

    def test_http404_django_counted(self):
        """D-PY10 : Http404 Django reconnu."""
        src = b'''
from django.http import Http404, JsonResponse

def my_view(request, item_id):
    if item_id < 0:
        raise Http404("Item not found")
    return JsonResponse({"id": item_id})
'''
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "python")
        # Http404 + JsonResponse = 2 exits
        assert r.by_type["exit"] == 2


# ===========================================================================
# Validation contre exemples manuel COSMIC v5.0 Part 3c MIS
# ===========================================================================

class TestCosmicManualExamples:
    """Lock-in tests pour les patterns canoniques du manuel COSMIC officiel.

    Ces tests verrouillent le comportement de Calibrix sur les exemples
    canoniques du manuel COSMIC v5.0 Part 3c MIS Examples. Si un de ces
    tests casse, vérifier le rapport VALIDATION_REPORT_MANUAL.md avant
    de modifier le test : le manuel COSMIC est l'étalon de référence.
    """

    def test_manual_2_1_8_dropdown_fp2(self):
        """Section 2.1.8 Ex 3 : Drop-down FP2 (3 CFP)."""
        src = b'''
from fastapi import FastAPI
from sqlalchemy.orm import Session
from sqlalchemy import select
app = FastAPI()

@app.get("/values/attr-z")
def display_values(session: Session = None):
    valid_values = session.scalars(select(ObjectB.z)).all()
    return {"values": list(valid_values)}
'''
        r = CosmicAnalyzer(mode="practical").analyze_source(src, "python")
        # 1 Entry + 1 Read + 1 Exit = 3 CFP
        assert r.total_cfp == 3, f"FUR : 3 CFP, got {r.total_cfp}"

    def test_manual_2_1_9_coding_create(self):
        """Section 2.1.9 Ex 4 : Coding system Create (4 CFP)."""
        src = b'''
from fastapi import FastAPI, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

class Payload(BaseModel):
    coding_system_id: int
    code: str
    description: str

app = FastAPI()

@app.post("/codes")
def create_code(payload: Payload, session: Session = None):
    if not (1 <= payload.coding_system_id <= 7):
        raise HTTPException(400, "Invalid coding system")
    new_code = Code(code=payload.code, description=payload.description)
    session.add(new_code)
    return {"id": new_code.id}
'''
        r = CosmicAnalyzer(mode="practical").analyze_source(src, "python")
        # 1 Entry + 1 Write + 1 Exit raise + 1 Exit return = 4 CFP
        # FUR : 2 Entry + 1 Write + 1 Exit error = 4 CFP (par convention différente
        # mais total identique)
        assert r.total_cfp == 4, f"FUR : 4 CFP, got {r.total_cfp}"

    def test_manual_3_1_1_simple_enquiry(self):
        """Section 3.1.1 Ex 1 : Simple enquiry orders (4 CFP, Calibrix : 3)."""
        src = b'''
from fastapi import FastAPI
from sqlalchemy.orm import Session
from sqlalchemy import select, func
app = FastAPI()

@app.get("/orders/by-period")
def orders_by_period(start: str, end: str, session: Session = None):
    rows = session.execute(
        select(Order.client_id, func.count(Order.id))
        .where(Order.date.between(start, end))
        .group_by(Order.client_id)
    ).all()
    return {"period": {"start": start, "end": end}, "clients": [...]}
'''
        r = CosmicAnalyzer(mode="practical").analyze_source(src, "python")
        # FUR : 4 CFP (2 Exits par frequency rule)
        # Calibrix : 3 CFP (1 Exit pour le return unique) — L10 gap connu
        assert r.total_cfp == 3, f"L10 gap : Calibrix attendu 3 CFP, got {r.total_cfp}"

    def test_manual_3_1_1_age_limit_fur1(self):
        """Section 3.1.1 Ex 4 FUR1 : Age limit enquiry simple (3 CFP)."""
        src = b'''
from fastapi import FastAPI
from sqlalchemy.orm import Session
from sqlalchemy import select
app = FastAPI()

@app.get("/employees/older")
def older_than(age: int, session: Session = None):
    employees = session.scalars(select(Employee).where(Employee.age > age)).all()
    return {"names": [e.name for e in employees]}
'''
        r = CosmicAnalyzer(mode="practical").analyze_source(src, "python")
        # 1 Entry + 1 Read + 1 Exit = 3 CFP (exact FUR)
        assert r.total_cfp == 3, f"FUR : 3 CFP, got {r.total_cfp}"


# ===========================================================================
# Robustesse : edge cases (verrouillés en régression)
# ===========================================================================

class TestPythonRobustness:
    """Edge cases qui ne doivent jamais crasher le détecteur Python.

    Ces tests verrouillent la dégradation gracieuse : un input dégénéré
    (vide, syntaxe invalide, unicode, imbrication profonde) doit retourner
    un résultat (souvent 0 CFP) plutôt que de lever une exception.
    """

    def _analyze(self, code: bytes):
        return CosmicAnalyzer(mode="practical").analyze_source(code, "python")

    def test_empty_file(self):
        assert self._analyze(b"").total_cfp == 0

    def test_only_comments(self):
        assert self._analyze(b"# comment\n# another").total_cfp == 0

    def test_syntax_error_degrades_gracefully(self):
        # Un fichier non parsable ne doit pas crasher : 0 CFP attendu
        assert self._analyze(b"def broken(:\n    pass").total_cfp == 0

    def test_deeply_nested_no_crash(self):
        # Construire une vraie imbrication (indentation croissante)
        lines = ["def f():"]
        for i in range(20):
            lines.append("    " * (i + 1) + "if True:")
        lines.append("    " * 21 + "x = session.get(M, 1)")
        code = "\n".join(lines).encode()
        r = self._analyze(code)
        # session.get détecté malgré 20 niveaux d'imbrication
        assert r.by_type.get("read", 0) == 1

    def test_unicode_identifiers(self):
        code = "def caf\u00e9(): return r\u00e9sum\u00e9".encode("utf-8")
        # Ne doit pas crasher sur des identifiants non-ASCII
        assert self._analyze(code).total_cfp == 0

    def test_walrus_operator_in_route(self):
        code = b"@app.get('/x')\ndef f():\n    if (u := session.get(User, 1)):\n        return u"
        r = self._analyze(code)
        # 1 entry + 1 read (walrus session.get) + 1 exit return = 3
        assert r.total_cfp == 3
        assert r.by_type["read"] == 1

    def test_nested_function_read_detected(self):
        code = b"def outer():\n    def inner():\n        return session.get(M, 1)\n    return inner"
        r = self._analyze(code)
        # session.get dans inner() détecté
        assert r.by_type.get("read", 0) == 1

    def test_async_generator_no_crash(self):
        code = b"async def gen():\n    async for x in source:\n        yield session.get(M, x)"
        r = self._analyze(code)
        assert r.by_type.get("read", 0) == 1

    def test_lambda_with_orm_call(self):
        code = b"f = lambda: session.get(Model, 1)"
        r = self._analyze(code)
        # session.get dans lambda détecté
        assert r.by_type.get("read", 0) == 1
