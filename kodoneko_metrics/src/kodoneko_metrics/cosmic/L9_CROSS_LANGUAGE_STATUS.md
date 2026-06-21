# L9 — Status par langage

**Date :** mai 2026
**Auteur :** Benoît Moraillon
**Objet :** Documentation transverse du fix L9 (error/confirmation messages comme Exit) sur Python, JS/TS, Java.

## Vue d'ensemble

Le fix L9 a été implémenté en trois temps :

| Date | Décision | Langage | Validation |
|---|---|---|---|
| Validation manuel COSMIC | D-PY10 | Python | ✅ 13 exemples, 95.2 % coverage |
| Phase de transposition | D-JS9 | JS/TS | 🧪 Revue logique adversariale (tree-sitter sandbox-absent) |
| Phase de transposition | D-JAVA14 | Java | 🧪 Revue logique adversariale (tree-sitter sandbox-absent) |

## Approche unifiée

Les trois langages utilisent la même architecture conceptuelle :

```
1. Pré-passe (collect_endpoint_method_bodies)
   ↓ Identifier les noeuds body de fonctions endpoint
   ↓ Stocker leurs ids dans collector.endpoint_method_bodies

2. Main pass (visit raise/throw)
   ↓ Si on est dans un body endpoint :
       Si exception dans whitelist HTTP :
           Si pas déjà émis pour cet endpoint :
               Émettre 1 Exit error (frequency rule)
```

## Whitelist par langage

### Python (D-PY10) — ~30 classes

```python
HTTP_EXCEPTION_CLASSES = {
    # FastAPI
    "HTTPException", "RequestValidationError", "WebSocketException",
    # Django
    "Http404", "PermissionDenied", "SuspiciousOperation", ...
    # Werkzeug/Flask
    "BadRequest", "NotFound", "Forbidden", "Conflict", ...
    # ~25 autres
}
```

Plus `abort(...)` (fonction Flask) traitée séparément.

### JavaScript/TypeScript (D-JS9) — 22 classes

```python
NESTJS_HTTP_EXCEPTIONS = {
    "HttpException",
    "BadRequestException", "UnauthorizedException", "NotFoundException",
    "ForbiddenException", "NotAcceptableException", "RequestTimeoutException",
    "ConflictException", "GoneException", "PayloadTooLargeException",
    "UnsupportedMediaTypeException", "UnprocessableEntityException",
    "InternalServerErrorException", "NotImplementedException",
    "BadGatewayException", "ServiceUnavailableException",
    "GatewayTimeoutException", "HttpVersionNotSupportedException",
    "MethodNotAllowedException", "PreconditionFailedException",
    "MisdirectedException", "ImATeapotException",
}
```

### Java (D-JAVA14) — 26 classes

```python
SPRING_HTTP_EXCEPTIONS = {
    # Spring Web
    "ResponseStatusException",
    # Spring REST client (5)
    "HttpClientErrorException", "HttpServerErrorException", ...
    # Spring Web validation (8)
    "MethodArgumentNotValidException", "MissingServletRequestParameterException", ...
    # JAX-RS / Jakarta REST (12)
    "WebApplicationException", "BadRequestException", "NotFoundException", ...
}
```

## Contextes endpoint reconnus

### Python (D-PY10)
- Fonctions décorées web (`@app.route`, `@app.get`, `@router.post`, etc.)
- Fonctions Django view (1er param = `request`)
- Détectées via `_is_web_endpoint` (heuristique de décorateurs)

### JavaScript/TypeScript (D-JS9)
- **NestJS** : méthodes décorées (`@Get`, `@Post`, `@Put`, etc.) dans une classe
- **Express/Fastify** : 2e arg d'un `app.get('/path', handler)` (arrow function ou function expression)
- **Routes file-based** : Next.js Pages API (`pages/api/**/*.ts`), App Router (`app/**/route.ts`), Remix (`app/routes/*`), SvelteKit (`+server.ts`)

### Java (D-JAVA14)
- **Spring Controllers** : méthodes avec `@GetMapping/@PostMapping/etc.` dans classe `@RestController/@Controller`
- **Listeners** : méthodes `@KafkaListener`, `@RabbitListener`, `@JmsListener`, `@SqsListener`, `@StreamListener`, `@EventListener`

## Frequency rule (manuel COSMIC section 2.6.1)

Le manuel COSMIC stipule : « Functional process A can potentially issue 2 distinct confirmation messages and 5 error messages to its functional users. Identify **one Exit** to account for all these (5 + 2 = 7) error/confirmation messages. »

**Application concrète :**

```python
@app.get("/users/{id}")
def get_user(id: int):
    if id < 0:
        raise HTTPException(400, "bad id")      # ① 1er throw → Exit émis
    if id > 1000:
        raise HTTPException(404, "not found")   # ② frequency rule → skip
    if id == 666:
        raise HTTPException(403, "forbidden")   # ③ frequency rule → skip
    return user  # ↓ 1 Exit return (séparé)
```

**Résultat** : 1 Entry + 1 Exit error + 1 Exit return = 3 CFP (avec D-PY10).
Sans D-PY10 : 1 Entry + 1 Exit return = 2 CFP (sous-comptage L9).

## Limitations communes (P2-P3)

### Exceptions custom héritant de la base

```typescript
// NestJS custom exception
export class UserNotFoundException extends NotFoundException {
    constructor(id: string) { super(`User ${id} not found`); }
}

// Usage dans controller
throw new UserNotFoundException(id);  // ❌ Non détecté (P2)
```

**Mitigation P2** : pré-passe pour collecter les classes ayant `extends HttpException` (JS/TS) ou `extends ResponseStatusException` (Java).

### @ResponseStatus sur exception custom Java

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
public class UserNotFoundException extends RuntimeException { }

// Usage
throw new UserNotFoundException();  // ❌ Non détecté (P2)
```

**Mitigation P2** : pré-passe pour collecter les classes annotées `@ResponseStatus` et étendre dynamiquement la whitelist.

### Express `next(error)`

```javascript
app.get('/x', (req, res, next) => {
    if (badCondition) next(new Error('failed'));
    // ...
});
```

Pattern minoritaire en Express moderne (la plupart utilisent `res.status(400).json(...)` couvert par D-JS6). Non implémenté en P1.

### Spring `@ExceptionHandler`

```java
@RestController
public class UserController {
    @GetMapping("/users/{id}")
    public User getUser(...) {
        return userService.findById(id);  // Peut throw UserNotFoundException
    }
    
    @ExceptionHandler(UserNotFoundException.class)
    public ResponseEntity<String> handle(UserNotFoundException e) {
        return ResponseEntity.notFound().build();
    }
}
```

Le throw vient du **service** (non-controller). Le handler renvoie une 404. Calibrix ne capture ni le throw (hors endpoint) ni le handler (non décoré comme endpoint). Hors scope P1.

## Tests unitaires

### Python (D-PY10) — 6 tests dans `TestPythonHTTPErrors`

- `test_raise_httpexception_in_fastapi_endpoint_counts_as_exit`
- `test_multiple_raises_same_endpoint_one_exit` (frequency rule)
- `test_raise_outside_endpoint_ignored` (garde-fou)
- `test_raise_valueerror_not_counted` (whitelist)
- `test_flask_abort_counted_as_exit`
- `test_http404_django_counted`

### JS/TS (D-JS9) et Java (D-JAVA14) — tests à ajouter à la livraison
Quand tree-sitter sera disponible dans l'environnement de validation, ajouter des tests équivalents :
- `test_throw_httpexception_in_nestjs_endpoint`
- `test_multiple_throws_same_endpoint_one_exit`
- `test_throw_outside_endpoint_ignored`
- `test_throw_valueerror_not_counted`

## Coefficient de calibration empirique

Le coefficient ×1.05 mesuré sur Python (13 exemples manuel COSMIC) devrait s'appliquer également à JS/TS et Java après portage. À valider empiriquement à la livraison sur des projets réels (Spring PetClinic, NestJS sample apps).

## Conclusion

**L9 est désormais traité de manière homogène sur les 3 langages** avec la même approche conceptuelle (pré-passe endpoints + whitelist + frequency rule). Cela représente une **parité multi-langage** importante pour l'usage Calibrix en consulting.

Les tests empiriques sur tree-sitter Java/JS restent à effectuer à la livraison ; les revues logiques adversariales (4 cas par langage) ne révèlent pas de bug structurel attendu.
