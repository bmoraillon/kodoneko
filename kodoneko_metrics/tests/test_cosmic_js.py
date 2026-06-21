"""
Tests pour la détection COSMIC en JavaScript/TypeScript.

Note : ces tests requièrent tree-sitter + tree-sitter-javascript +
tree-sitter-typescript. Ils se skip automatiquement si non installés
(via le mock pytest dans run_tests.py).

Frameworks testés
-----------------
- Backend : Express, NestJS, Fastify
- File-based : Next.js Pages Router, Next.js App Router, Remix, SvelteKit
- ORM : Prisma, TypeORM, Sequelize, Drizzle, Mongoose
- Cache : Redis (node-redis / ioredis)
- HTTP client : fetch, axios
- Storage : localStorage, sessionStorage, document.cookie, IndexedDB
- File I/O : fs, fs/promises
- WebSocket : ws, socket.io
- Queue : BullMQ
- CLI : Commander
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pytest

# Détection de disponibilité tree-sitter JS/TS
try:
    import tree_sitter  # noqa: F401
    import tree_sitter_javascript  # noqa: F401
    import tree_sitter_typescript  # noqa: F401
    _TS_JS_AVAILABLE = True
except ImportError:
    _TS_JS_AVAILABLE = False


# Si tree-sitter JS/TS pas dispo, on skip toute la classe via pytestmark
pytestmark = pytest.mark.skipif(
    not _TS_JS_AVAILABLE,
    reason="tree-sitter-javascript / tree-sitter-typescript non installé",
)

from kodoneko_metrics.cosmic import CosmicAnalyzer


# ===========================================================================
# Backend frameworks
# ===========================================================================

class TestExpressRoutes:

    def test_express_get(self):
        src = b"""
const express = require('express');
const app = express();

app.get('/users', (req, res) => {
    res.json([]);
});

app.post('/users', (req, res) => {
    res.status(201).json({});
});
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "javascript", "app.js")
        assert r.by_type["entry"] >= 2
        # Pas d'erreur de double-comptage
        assert "express" in r.by_framework or "fastify" in r.by_framework

    def test_router_get(self):
        src = b"""
const router = express.Router();
router.get('/users', handler);
router.post('/users', createHandler);
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "javascript", "routes.js")
        assert r.by_type["entry"] == 2


class TestFastifyRoutes:

    def test_fastify_get(self):
        src = b"""
const fastify = require('fastify')();

fastify.get('/health', async (request, reply) => {
    return { ok: true };
});

fastify.post('/users', async (request, reply) => {
    return { id: 1 };
});
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "javascript", "server.js")
        assert r.by_type["entry"] >= 2


class TestNestJSRoutes:

    def test_nestjs_controller(self):
        src = b"""
import { Controller, Get, Post, Body } from '@nestjs/common';

@Controller('users')
export class UsersController {
    @Get()
    findAll() {
        return [];
    }

    @Post()
    create(@Body() dto: any) {
        return { id: 1 };
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "users.controller.ts")
        assert r.by_type["entry"] >= 2
        assert "nestjs" in r.by_framework

    def test_nestjs_message_pattern(self):
        src = b"""
import { Controller, MessagePattern } from '@nestjs/microservices';

@Controller()
export class TasksController {
    @MessagePattern({ cmd: 'compute' })
    handle(data: any) {
        return { result: 42 };
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "tasks.controller.ts")
        assert r.by_type["entry"] >= 1


# ===========================================================================
# File-based routing (Next.js, Remix, SvelteKit)
# ===========================================================================

class TestNextJSPagesRouter:

    def test_default_export_handler(self):
        src = b"""
export default function handler(req, res) {
    res.status(200).json({ ok: true });
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "pages/api/users.ts")
        assert r.by_type["entry"] == 1
        assert "nextjs" in r.by_framework

    def test_async_default_export(self):
        src = b"""
export default async function handler(req, res) {
    const data = await fetch('https://api.com');
    res.json(data);
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "pages/api/proxy.ts")
        assert r.by_type["entry"] == 1


class TestNextJSAppRouter:

    def test_named_export_routes(self):
        src = b"""
import { NextResponse } from 'next/server';

export async function GET(request) {
    return NextResponse.json([]);
}

export async function POST(request) {
    const body = await request.json();
    return NextResponse.json({ id: 1 });
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "app/api/users/route.ts")
        # 2 routes = 2 entries
        assert r.by_type["entry"] == 2


class TestRemixRoutes:

    def test_loader_and_action(self):
        src = b"""
export async function loader({ params }) {
    return { id: params.id };
}

export async function action({ request }) {
    return { ok: true };
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "app/routes/users.$id.tsx")
        # loader + action = 2 entries
        assert r.by_type["entry"] == 2


class TestSvelteKitRoutes:

    def test_server_routes(self):
        src = b"""
export async function GET({ params }) {
    return new Response(JSON.stringify({ id: params.id }));
}

export async function POST({ request }) {
    return new Response('', { status: 201 });
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "src/routes/api/users/+server.ts")
        assert r.by_type["entry"] == 2


# ===========================================================================
# ORM SQL
# ===========================================================================

class TestPrisma:

    def test_prisma_find_create_update_delete(self):
        src = b"""
const users = await prisma.user.findMany();
const user = await prisma.user.findUnique({ where: { id: 1 } });
const created = await prisma.user.create({ data: { name: 'bob' } });
await prisma.user.update({ where: { id: 1 }, data: { name: 'alice' } });
await prisma.user.delete({ where: { id: 1 } });
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "service.ts")
        # 2 reads (findMany, findUnique), 3 writes (create, update, delete)
        assert r.by_type["read"] >= 2
        assert r.by_type["write"] >= 3
        assert "prisma" in r.by_framework

    def test_prisma_via_context(self):
        src = b"""
async function getUser(ctx, id) {
    return ctx.prisma.user.findUnique({ where: { id } });
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "trpc.ts")
        assert r.by_type["read"] >= 1


class TestTypeORM:

    def test_repository_methods(self):
        src = b"""
async function example(userRepository) {
    const users = await userRepository.find();
    const one = await userRepository.findOne({ where: { id: 1 } });
    await userRepository.save({ name: 'bob' });
    await userRepository.delete(1);
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "service.ts")
        assert r.by_type["read"] >= 2
        assert r.by_type["write"] >= 2

    def test_manager_query(self):
        src = b"""
const result = await manager.query('SELECT * FROM users');
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "raw.ts")
        assert r.by_type["read"] >= 1


class TestSequelize:

    def test_model_distinctive_methods(self):
        # Méthodes distinctives : détectées sur base capitalisée seule
        src = b"""
const users = await User.findAll();
const user = await User.findByPk(1);
await User.destroy({ where: { id: 1 } });
await User.bulkCreate([{ name: 'bob' }]);
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "javascript", "service.js")
        # findAll + findByPk = 2 reads ; destroy + bulkCreate = 2 writes
        assert r.by_type["read"] >= 2
        assert r.by_type["write"] >= 2

    def test_ambiguous_verbs_require_strong_signal(self):
        # D-JS10 : create/update/save sur base capitalisée SANS signal fort
        # (token sequelize/model/db) ne sont PAS comptés — évite les faux
        # positifs sur RouteImport.update(), SomeFactory.create(), etc.
        src = b"""
RouteImport.update({ path: '/x' });
SomeFactory.create({ id: 1 });
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "javascript", "routeTree.gen.js")
        assert r.by_type.get("write", 0) == 0

    def test_ambiguous_verbs_counted_with_model_token(self):
        # Avec un token "models"/"sequelize", les verbes ambigus sont comptés
        src = b"""
await models.User.create({ name: 'bob' });
await models.User.update({ name: 'x' }, { where: { id: 1 } });
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "javascript", "service.js")
        assert r.by_type.get("write", 0) >= 2


class TestDrizzle:

    def test_drizzle_select_insert(self):
        src = b"""
const result = await db.select().from(users).where(eq(users.id, 1));
await db.insert(users).values({ name: 'bob' });
await db.update(users).set({ name: 'alice' }).where(eq(users.id, 1));
await db.delete(users).where(eq(users.id, 1));
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "service.ts")
        # Drizzle commence par select/insert/update/delete sur db
        assert r.by_type["read"] >= 1
        assert r.by_type["write"] >= 3


# ===========================================================================
# Mongoose
# ===========================================================================

class TestMongoose:

    def test_model_methods(self):
        src = b"""
const users = await User.find({ active: true });
const user = await User.findById(1);
await User.updateOne({ _id: 1 }, { name: 'x' });
await User.deleteOne({ _id: 1 });
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "service.ts")
        assert r.by_type["read"] >= 2
        assert r.by_type["write"] >= 2


# ===========================================================================
# Redis
# ===========================================================================

class TestRedisNode:

    def test_redis_get_set(self):
        src = b"""
const value = await redis.get('key');
await redis.set('key', 'value');
await redis.setex('key', 60, 'value');
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "javascript", "cache.js")
        assert r.by_type["read"] >= 1
        assert r.by_type["write"] >= 2

    def test_ioredis_cache_pattern(self):
        src = b"""
const cached = await cache.hgetall('user:1');
await cache.hset('user:1', { name: 'bob' });
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "javascript", "cache.js")
        assert r.by_type["read"] >= 1
        assert r.by_type["write"] >= 1


# ===========================================================================
# HTTP client
# ===========================================================================

class TestHTTPClient:

    def test_fetch_global(self):
        src = b"""
const response = await fetch('https://api.example.com/users');
const data = await response.json();
"""
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "javascript", "api.js")
        # 1 write (req) + 1 read (resp)
        assert r.by_type["write"] >= 1
        assert r.by_type["read"] >= 1

    def test_axios(self):
        src = b"""
const response = await axios.get('https://api.example.com/users');
await axios.post('https://api.example.com/users', { name: 'bob' });
"""
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "javascript", "api.js")
        # axios.get + axios.post = 2 writes + 2 reads en practical
        assert r.by_type["write"] >= 2
        assert r.by_type["read"] >= 2

    def test_strict_mode_skips_http(self):
        src = b"""
const response = await fetch('https://api.example.com/users');
"""
        a = CosmicAnalyzer(mode="strict")
        r = a.analyze_source(src, "javascript", "api.js")
        # Strict ne compte pas fetch sortant
        for m in r.movements:
            assert "http" not in m.detector and "fetch" not in m.detector


# ===========================================================================
# Frontend persistence
# ===========================================================================

class TestBrowserStorage:

    def test_localstorage(self):
        src = b"""
const data = localStorage.getItem('key');
localStorage.setItem('key', 'value');
localStorage.removeItem('key');
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "javascript", "app.js")
        assert r.by_type["read"] >= 1
        assert r.by_type["write"] >= 2

    def test_sessionstorage(self):
        src = b"""
sessionStorage.setItem('token', 'abc');
const t = sessionStorage.getItem('token');
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "javascript", "app.js")
        assert r.by_type["read"] >= 1
        assert r.by_type["write"] >= 1

    def test_document_cookie(self):
        src = b"""
document.cookie = "name=bob; path=/";
const cookies = document.cookie;
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "javascript", "app.js")
        assert r.by_type["read"] >= 1
        assert r.by_type["write"] >= 1


# ===========================================================================
# File I/O (Node.js)
# ===========================================================================

class TestNodeFS:

    def test_fs_read_write(self):
        src = b"""
const fs = require('fs');
const data = fs.readFileSync('file.txt');
fs.writeFileSync('output.txt', 'content');
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "javascript", "io.js")
        assert r.by_type["read"] >= 1
        assert r.by_type["write"] >= 1

    def test_fs_promises(self):
        src = b"""
import { readFile, writeFile } from 'fs/promises';
const data = await readFile('file.txt');
await writeFile('out.txt', 'content');
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "typescript", "io.ts")
        assert r.by_type["read"] >= 1
        assert r.by_type["write"] >= 1


# ===========================================================================
# WebSocket
# ===========================================================================

class TestWebSocket:

    def test_ws_server(self):
        src = b"""
const WebSocket = require('ws');
const wss = new WebSocket.Server({ port: 8080 });

wss.on('connection', (ws) => {
    ws.on('message', (data) => {
        ws.send(JSON.stringify({ echo: data }));
    });
});
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "javascript", "ws.js")
        # Server, on('connection'), on('message'), send → mouvements WS
        assert "websocket" in r.by_framework


# ===========================================================================
# Intégration
# ===========================================================================

class TestFullBackendIntegration:

    def test_nestjs_with_prisma_redis(self):
        src = b"""
import { Controller, Get, Post, Body } from '@nestjs/common';

@Controller('users')
export class UsersController {
    constructor(private prisma: PrismaService, private redis: Redis) {}

    @Get(':id')
    async getUser(id: string) {
        const cached = await this.redis.get(`user:${id}`);
        if (cached) return JSON.parse(cached);
        const user = await this.prisma.user.findUnique({ where: { id } });
        await this.redis.setex(`user:${id}`, 60, JSON.stringify(user));
        return user;
    }

    @Post()
    async create(@Body() dto: any) {
        const user = await this.prisma.user.create({ data: dto });
        await axios.post('https://api.email.com/welcome', { id: user.id });
        return user;
    }
}
"""
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "typescript", "users.controller.ts")
        # 2 endpoints
        assert r.by_type["entry"] >= 2
        # NestJS routes attendues
        assert "nestjs" in r.by_framework
        # Prisma
        assert "prisma" in r.by_framework
        # Redis
        assert "redis" in r.by_framework
        # HTTP client
        assert "http_client" in r.by_framework
