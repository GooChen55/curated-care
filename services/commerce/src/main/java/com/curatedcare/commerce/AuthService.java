package com.curatedcare.commerce;

import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AuthService {
    public record User(long id, String username, String role) {}
    private final JdbcTemplate db;
    private final SecureRandom random = new SecureRandom();
    public AuthService(JdbcTemplate db) { this.db = db; }
    public String hashPassword(String password) {
        byte[] salt = new byte[16]; random.nextBytes(salt);
        return Base64.getEncoder().encodeToString(salt) + ":" + derive(password, salt);
    }
    private String derive(String password, byte[] salt) {
        try {
            var spec = new PBEKeySpec(password.toCharArray(), salt, 120000, 256);
            byte[] bytes = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
            spec.clearPassword(); return Base64.getEncoder().encodeToString(bytes);
        } catch (Exception e) { throw new IllegalStateException(e); }
    }
    public static String digest(String input) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(input.getBytes(StandardCharsets.UTF_8))); }
        catch (Exception e) { throw new IllegalStateException(e); }
    }
    public Map<String,Object> login(String username, String password) {
        var users = db.queryForList("SELECT * FROM customers WHERE username=?", username);
        if (users.isEmpty()) throw error(401,"用户名或密码错误");
        var row = users.get(0); String[] encoded = row.get("password_hash").toString().split(":");
        if (!MessageDigest.isEqual(derive(password, Base64.getDecoder().decode(encoded[0])).getBytes(StandardCharsets.UTF_8), encoded[1].getBytes(StandardCharsets.UTF_8))) throw error(401,"用户名或密码错误");
        byte[] secret = new byte[32]; random.nextBytes(secret);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(secret);
        db.update("DELETE FROM auth_sessions WHERE expires_at < ?", System.currentTimeMillis());
        db.update("INSERT INTO auth_sessions VALUES(?,?,?)", digest(token), row.get("id"), System.currentTimeMillis()+86400000);
        return Map.of("token",token,"user",new User(((Number)row.get("id")).longValue(),username,row.get("role").toString()));
    }
    public User user(HttpServletRequest request) {
        String value=request.getHeader("Authorization");
        if (value==null || !value.startsWith("Bearer ")) throw error(401,"请先登录");
        var rows=db.queryForList("SELECT c.id,c.username,c.role FROM customers c JOIN auth_sessions s ON c.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?", digest(value.substring(7)), System.currentTimeMillis());
        if (rows.isEmpty()) throw error(401,"登录已过期");
        var row=rows.get(0); return new User(((Number)row.get("id")).longValue(),row.get("username").toString(),row.get("role").toString());
    }
    public User admin(HttpServletRequest request) { var u=user(request); if(!u.role().equals("ADMIN")) throw error(403,"需要管理员权限"); return u; }
    public void logout(HttpServletRequest request) { user(request); db.update("DELETE FROM auth_sessions WHERE token_hash=?",digest(request.getHeader("Authorization").substring(7))); }
    public static ResponseStatusException error(int status,String text) { return new ResponseStatusException(HttpStatus.valueOf(status),text); }
}
