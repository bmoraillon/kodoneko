"""
Tests pour la détection COSMIC en Java.

Note : ces tests requièrent tree-sitter + tree-sitter-java. Ils se skip
automatiquement si non installés.

Frameworks testés
-----------------
- Spring Web : @RestController + @GetMapping, @PostMapping, @PutMapping,
  @DeleteMapping, @PatchMapping, @RequestMapping
- Spring Data JPA : repository.findX/saveX/deleteX
- JPA EntityManager : find/persist/merge/remove
- JDBC : PreparedStatement.executeQuery/executeUpdate
- Spring JdbcTemplate : query/queryForObject/update
- Messaging : @KafkaListener, @RabbitListener, KafkaTemplate.send,
  RabbitTemplate.convertAndSend
- HTTP client : RestTemplate, WebClient, HttpClient (Java 11+)
- Redis : RedisTemplate.opsForValue/opsForHash + get/set
- File I/O : Files.readString/writeString, new FileReader/FileWriter
- picocli : @Command
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pytest

# Détection de disponibilité tree-sitter Java
try:
    import tree_sitter  # noqa: F401
    import tree_sitter_java  # noqa: F401
    _TS_JAVA_AVAILABLE = True
except ImportError:
    _TS_JAVA_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not _TS_JAVA_AVAILABLE,
    reason="tree-sitter-java non installé",
)

from kodoneko_metrics.cosmic import CosmicAnalyzer


# ===========================================================================
# Spring REST controllers
# ===========================================================================

class TestSpringRestControllers:

    def test_rest_controller_get(self):
        src = b"""
package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/users")
public class UserController {

    @GetMapping("/{id}")
    public User getOne(@PathVariable Long id) {
        return new User();
    }

    @PostMapping
    public User create(@RequestBody UserDto dto) {
        return new User();
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "UserController.java")
        # 2 endpoints
        assert r.by_type["entry"] >= 2
        assert r.by_type["exit"] >= 2  # 2 returns
        assert "spring" in r.by_framework

    def test_all_http_verbs(self):
        src = b"""
@RestController
public class C {
    @GetMapping("/a") public String a() { return "a"; }
    @PostMapping("/b") public String b() { return "b"; }
    @PutMapping("/c") public String c() { return "c"; }
    @DeleteMapping("/d") public String d() { return "d"; }
    @PatchMapping("/e") public String e() { return "e"; }
    @RequestMapping("/f") public String f() { return "f"; }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "C.java")
        # 6 endpoints
        assert r.by_type["entry"] == 6

    def test_non_controller_class_ignored(self):
        """Une classe sans @RestController : pas d'endpoints détectés."""
        src = b"""
@Service
public class UserService {
    @Transactional
    public User getOne(Long id) {
        return new User();
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "UserService.java")
        # Pas de @GetMapping etc. donc pas d'entry
        for m in r.movements:
            assert m.type != "entry" or "listener" in m.detector


# ===========================================================================
# Spring Data JPA
# ===========================================================================

class TestSpringDataJPA:

    def test_repository_methods(self):
        src = b"""
public class Service {
    private final UserRepository userRepository;

    public void example() {
        User u = userRepository.findById(1L).orElseThrow();
        List<User> all = userRepository.findAll();
        long n = userRepository.count();
        userRepository.save(u);
        userRepository.deleteById(1L);
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "Service.java")
        # 3 reads (findById, findAll, count), 2 writes (save, deleteById)
        assert r.by_type["read"] >= 3
        assert r.by_type["write"] >= 2
        assert "spring_data_jpa" in r.by_framework

    def test_derived_method_names(self):
        """findByEmail, deleteByActiveFalse, etc."""
        src = b"""
public class Service {
    void doIt(UserRepository repo) {
        repo.findByEmail("a@b.com");
        repo.findByActiveTrueAndAgeGreaterThan(18);
        repo.deleteByEmail("a@b.com");
        repo.countByActiveTrue();
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "Service.java")
        assert r.by_type["read"] >= 3  # findByEmail, findByActiveTrue..., countByActiveTrue
        assert r.by_type["write"] >= 1  # deleteByEmail


# ===========================================================================
# JPA EntityManager
# ===========================================================================

class TestJPAEntityManager:

    def test_entity_manager_methods(self):
        src = b"""
public class Repo {
    private final EntityManager entityManager;

    public User findOne(Long id) {
        User u = entityManager.find(User.class, id);
        entityManager.persist(new User());
        entityManager.merge(u);
        entityManager.remove(u);
        return u;
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "Repo.java")
        # 1 read (find), 3 writes (persist, merge, remove)
        assert r.by_type["read"] >= 1
        assert r.by_type["write"] >= 3
        assert "jpa" in r.by_framework


# ===========================================================================
# JDBC
# ===========================================================================

class TestJDBC:

    def test_prepared_statement(self):
        src = b"""
public class Dao {
    public List<User> findAll(Connection conn) throws Exception {
        PreparedStatement stmt = conn.prepareStatement("SELECT * FROM users");
        ResultSet rs = stmt.executeQuery();
        return mapResults(rs);
    }

    public int insert(Connection conn) throws Exception {
        PreparedStatement stmt = conn.prepareStatement("INSERT INTO users VALUES (?)");
        return stmt.executeUpdate();
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "Dao.java")
        assert r.by_type["read"] >= 1
        assert r.by_type["write"] >= 1
        assert "jdbc" in r.by_framework


class TestJdbcTemplate:

    def test_spring_jdbc_template(self):
        src = b"""
public class Dao {
    private final JdbcTemplate jdbcTemplate;

    public List<User> findAll() {
        return jdbcTemplate.query("SELECT * FROM users", userRowMapper);
    }

    public User findOne(Long id) {
        return jdbcTemplate.queryForObject("SELECT * FROM users WHERE id = ?",
                                            userRowMapper, id);
    }

    public int updateName(Long id, String name) {
        return jdbcTemplate.update("UPDATE users SET name = ? WHERE id = ?",
                                    name, id);
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "Dao.java")
        assert r.by_type["read"] >= 2
        assert r.by_type["write"] >= 1
        assert "jdbc_template" in r.by_framework


# ===========================================================================
# Spring Kafka / RabbitMQ / JMS
# ===========================================================================

class TestSpringMessaging:

    def test_kafka_listener(self):
        src = b"""
@Service
public class OrderListener {
    @KafkaListener(topics = "orders")
    public void onOrder(Order order) {
        process(order);
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "OrderListener.java")
        assert r.by_type["entry"] >= 1
        assert "kafka" in r.by_framework

    def test_rabbit_listener(self):
        src = b"""
@Service
public class TaskListener {
    @RabbitListener(queues = "tasks")
    public void onTask(Task t) {
        process(t);
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "TaskListener.java")
        assert r.by_type["entry"] >= 1
        assert "rabbitmq" in r.by_framework

    def test_kafka_template_send(self):
        src = b"""
public class Producer {
    private final KafkaTemplate<String, Order> kafkaTemplate;

    public void publish(Order o) {
        kafkaTemplate.send("orders", o.getId(), o);
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "Producer.java")
        assert r.by_type["exit"] >= 1
        assert "kafka" in r.by_framework

    def test_rabbit_template_convert_and_send(self):
        src = b"""
public class Producer {
    private final RabbitTemplate rabbitTemplate;

    public void publish(Task t) {
        rabbitTemplate.convertAndSend("exchange", "routingKey", t);
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "Producer.java")
        assert r.by_type["exit"] >= 1
        assert "rabbitmq" in r.by_framework


# ===========================================================================
# HTTP client
# ===========================================================================

class TestHTTPClient:

    def test_rest_template_practical(self):
        src = b"""
public class Client {
    private final RestTemplate restTemplate;

    public User fetch(Long id) {
        return restTemplate.getForObject("https://api.com/users/" + id, User.class);
    }

    public void post(User u) {
        restTemplate.postForObject("https://api.com/users", u, User.class);
    }
}
"""
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "java", "Client.java")
        # 2 calls × (1 write + 1 read) = 4 mouvements HTTP
        assert r.by_type["write"] >= 2
        assert r.by_type["read"] >= 2
        assert "rest_template" in r.by_framework

    def test_rest_template_strict(self):
        src = b"""
public class Client {
    private final RestTemplate restTemplate;
    public User fetch(Long id) {
        return restTemplate.getForObject("https://api.com", User.class);
    }
}
"""
        a = CosmicAnalyzer(mode="strict")
        r = a.analyze_source(src, "java", "Client.java")
        # Strict ne compte pas les calls HTTP sortants
        for m in r.movements:
            assert "rest_template" not in m.detector


# ===========================================================================
# Redis (RedisTemplate)
# ===========================================================================

class TestRedis:

    def test_ops_for_value(self):
        src = b"""
public class Cache {
    private final RedisTemplate<String, String> redisTemplate;

    public String get(String key) {
        return redisTemplate.opsForValue().get(key);
    }

    public void set(String key, String value) {
        redisTemplate.opsForValue().set(key, value);
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "Cache.java")
        assert r.by_type["read"] >= 1
        assert r.by_type["write"] >= 1
        assert "redis" in r.by_framework


# ===========================================================================
# File I/O
# ===========================================================================

class TestFilesIO:

    def test_files_read_write(self):
        src = b"""
import java.nio.file.Files;
import java.nio.file.Path;

public class Config {
    public String load(Path p) throws Exception {
        return Files.readString(p);
    }

    public void save(Path p, String content) throws Exception {
        Files.writeString(p, content);
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "Config.java")
        assert r.by_type["read"] >= 1
        assert r.by_type["write"] >= 1
        assert "stdlib_java" in r.by_framework

    def test_new_file_reader_writer(self):
        src = b"""
public class IO {
    public void read() throws Exception {
        BufferedReader r = new BufferedReader(new FileReader("input.txt"));
    }

    public void write() throws Exception {
        BufferedWriter w = new BufferedWriter(new FileWriter("output.txt"));
    }
}
"""
        a = CosmicAnalyzer()
        r = a.analyze_source(src, "java", "IO.java")
        assert r.by_type["read"] >= 1
        assert r.by_type["write"] >= 1


# ===========================================================================
# Intégration : Spring controller complet
# ===========================================================================

class TestFullSpringIntegration:

    def test_realistic_spring_app(self):
        src = b"""
package com.example.users;

import org.springframework.web.bind.annotation.*;
import org.springframework.data.repository.CrudRepository;

@RestController
@RequestMapping("/api/users")
public class UserController {
    private final UserRepository userRepository;
    private final RedisTemplate<String, User> redisTemplate;
    private final KafkaTemplate<String, UserEvent> kafkaTemplate;
    private final RestTemplate restTemplate;

    @GetMapping("/{id}")
    public User getOne(@PathVariable Long id) {
        User cached = redisTemplate.opsForValue().get("user:" + id);
        if (cached != null) return cached;
        User u = userRepository.findById(id).orElseThrow();
        redisTemplate.opsForValue().set("user:" + id, u);
        return u;
    }

    @PostMapping
    public User create(@RequestBody User u) {
        User saved = userRepository.save(u);
        kafkaTemplate.send("user-created", saved.getId().toString(), new UserEvent(saved));
        restTemplate.postForObject("https://api.email.com/welcome", saved, Void.class);
        return saved;
    }

    @DeleteMapping("/{id}")
    public void delete(@PathVariable Long id) {
        userRepository.deleteById(id);
        redisTemplate.delete("user:" + id);
    }
}
"""
        a = CosmicAnalyzer(mode="practical")
        r = a.analyze_source(src, "java", "UserController.java")
        # 3 endpoints
        assert r.by_type["entry"] >= 3
        # Frameworks attendus
        assert "spring" in r.by_framework
        assert "spring_data_jpa" in r.by_framework
        assert "redis" in r.by_framework
        assert "kafka" in r.by_framework
        assert "rest_template" in r.by_framework
