package com.curatedcare.commerce;

import java.math.BigDecimal;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.ResponseEntity;
import static com.curatedcare.commerce.AuthService.error;

@RestController
@RequestMapping("/api")
public class CommerceController {
    private final CommerceService commerce; private final AuthService auth; private final ObjectMapper json;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    @Value("${care.demo}") private boolean demo;
    @Value("${care.assistant-url}") private String assistantUrl;
    @Value("${care.knowledge-url}") private String knowledgeUrl;
    @Value("${care.service-token}") private String serviceToken;
    public CommerceController(CommerceService commerce,AuthService auth,ObjectMapper json){this.commerce=commerce;this.auth=auth;this.json=json;}
    record Login(@NotBlank @Size(max=80) String username,@NotBlank @Size(max=200) String password) {}
    record Cart(@Min(0) @Max(99) int quantity) {}
    record Checkout(@NotBlank @Size(min=5,max=300) String address) {}
    record Refund(@NotBlank @Size(min=2,max=500) String reason) {}
    record Review(boolean approve,@Size(max=500) String note) {}
    record Product(@NotBlank @Size(max=200) String title,@NotBlank @Size(max=80) String category,@NotBlank @Size(max=2000) String description,@NotNull BigDecimal price,@Min(0) int stock,boolean active) {}
    private Map<String,Object> data(Object value) { return Map.of("data",value); }
    @GetMapping("/health") public Object health(){return data(Map.of("service","commerce","demo",demo));}
    @PostMapping("/auth/login") public Object login(@Valid @RequestBody Login b){return data(auth.login(b.username(),b.password()));}
    @PostMapping("/auth/logout") public Object logout(HttpServletRequest r){auth.logout(r);return data(true);}
    @GetMapping("/me") public Object me(HttpServletRequest r){return data(auth.user(r));}
    @GetMapping("/products") public Object products(){return data(commerce.products());}
    @GetMapping("/products/{id}") public Object product(@PathVariable long id){return data(commerce.product(id));}
    @GetMapping("/cart") public Object cart(HttpServletRequest r){return data(commerce.cart(auth.user(r).id()));}
    @PutMapping("/cart/{id}") public Object cart(HttpServletRequest r,@PathVariable long id,@Valid @RequestBody Cart b){commerce.putCart(auth.user(r).id(),id,b.quantity());return cart(r);}
    @GetMapping("/orders") public Object orders(HttpServletRequest r){return data(commerce.orders(auth.user(r).id()));}
    @GetMapping("/orders/{id}") public Object order(HttpServletRequest r,@PathVariable String id){return data(commerce.order(auth.user(r).id(),id));}
    @PostMapping("/orders") public Object checkout(HttpServletRequest r,@Valid @RequestBody Checkout b,@RequestHeader("Idempotency-Key") String key){return data(commerce.checkout(auth.user(r).id(),b.address(),key));}
    @PostMapping("/orders/{id}/demo-pay") public Object pay(HttpServletRequest r,@PathVariable String id){var u=auth.user(r);if(!demo)throw error(403,"演示支付已关闭");return data(commerce.pay(u.id(),id));}
    @PostMapping("/orders/{id}/cancel") public Object cancel(HttpServletRequest r,@PathVariable String id){return data(commerce.cancel(auth.user(r).id(),id));}
    @GetMapping("/orders/{id}/logistics") public Object logistics(HttpServletRequest r,@PathVariable String id){return data(commerce.logistics(auth.user(r).id(),id));}
    @PostMapping("/orders/{id}/refund-applications") public Object refund(HttpServletRequest r,@PathVariable String id,@Valid @RequestBody Refund b,@RequestHeader("Idempotency-Key") String key){return data(commerce.refund(auth.user(r).id(),id,b.reason(),key));}
    @GetMapping("/admin/orders") public Object adminOrders(HttpServletRequest r){auth.admin(r);return data(commerce.adminOrders());}
    @GetMapping("/admin/refunds") public Object refunds(HttpServletRequest r){auth.admin(r);return data(commerce.refunds());}
    @GetMapping("/admin/products") public Object allProducts(HttpServletRequest r){auth.admin(r);return data(commerceProducts());}
    private Object commerceProducts(){return commerce.allProducts();}
    @PutMapping("/admin/products/{id}") public Object save(HttpServletRequest r,@PathVariable @Min(1) long id,@Valid @RequestBody Product b){commerce.saveProduct(auth.admin(r).id(),id,b.title(),b.category(),b.description(),b.price(),b.stock(),b.active());return data(true);}
    @PostMapping("/admin/orders/{id}/ship") public Object ship(HttpServletRequest r,@PathVariable String id){commerce.ship(auth.admin(r).id(),id);return data(true);}
    @PostMapping("/admin/refunds/{id}/review") public Object review(HttpServletRequest r,@PathVariable String id,@Valid @RequestBody Review b){return data(commerce.review(auth.admin(r).id(),id,b.approve(),b.note()));}
    @PostMapping("/assistant/chat") public Object chat(HttpServletRequest r,@RequestBody Map<String,Object> b){auth.user(r);return proxy(assistantUrl+"/chat","POST",b,r.getHeader("Authorization"));}
    @GetMapping("/assistant/history") public Object history(HttpServletRequest r){auth.user(r);return proxy(assistantUrl+"/history","GET",null,r.getHeader("Authorization"));}
    @GetMapping("/admin/knowledge") public Object documents(HttpServletRequest r){auth.admin(r);return proxy(knowledgeUrl+"/documents","GET",null,null);}
    @PostMapping("/admin/knowledge") public Object document(HttpServletRequest r,@RequestBody Map<String,Object> b){auth.admin(r);return proxy(knowledgeUrl+"/documents","POST",b,null);}
    @DeleteMapping("/admin/knowledge/{id}") public Object remove(HttpServletRequest r,@PathVariable String id){auth.admin(r);if(!id.matches("[a-f0-9]{64}"))throw error(400,"文档标识不合法");return proxy(knowledgeUrl+"/documents/"+id,"DELETE",null,null);}
    private Object proxy(String url,String method,Object body,String authorization){
        try {
            var builder=HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(70)).header("Content-Type","application/json");
            if(authorization!=null)builder.header("Authorization",authorization);else builder.header("X-Service-Token",serviceToken);
            builder.method(method,body==null?HttpRequest.BodyPublishers.noBody():HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body)));
            var response=http.send(builder.build(),HttpResponse.BodyHandlers.ofString());
            return ResponseEntity.status(response.statusCode()).header("Content-Type","application/json").body(response.body());
        }catch(Exception e){if(e instanceof InterruptedException)Thread.currentThread().interrupt();throw error(502,"AI 服务暂时不可用，请检查服务状态");}
    }
    @RestControllerAdvice
    static class Errors {
        @ExceptionHandler(ResponseStatusException.class) ResponseEntity<?> errorResponse(ResponseStatusException e){return ResponseEntity.status(e.getStatusCode()).body(Map.of("detail",Objects.requireNonNullElse(e.getReason(),"请求失败")));}
        @ExceptionHandler(org.springframework.web.bind.MethodArgumentNotValidException.class) ResponseEntity<?> validation(Exception e){return ResponseEntity.badRequest().body(Map.of("detail","参数不合法，请检查输入长度和数值"));}
    }
}
