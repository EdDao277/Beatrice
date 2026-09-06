package com.beatrice.backend.team;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.*;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

/** Return useful messages without leaking SQL, credentials, or stack traces. */
@RestControllerAdvice(assignableTypes=TeamController.class)
public class TeamErrors {
    @ExceptionHandler(DuplicateKeyException.class)
    ResponseEntity<ProblemDetail> duplicate() {
        return problem(HttpStatus.CONFLICT, "A team with that name already exists (capitalization is ignored).");
    }
    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> validation() {
        return problem(HttpStatus.BAD_REQUEST, "Check the team name, five roster roles, and comfort values (1–10).");
    }
    @ExceptionHandler(ResponseStatusException.class)
    ResponseEntity<ProblemDetail> status(ResponseStatusException error) {
        return ResponseEntity.status(error.getStatusCode()).body(
            ProblemDetail.forStatusAndDetail(error.getStatusCode(), error.getReason()));
    }
    private ResponseEntity<ProblemDetail> problem(HttpStatus status, String detail) {
        return ResponseEntity.status(status).body(ProblemDetail.forStatusAndDetail(status, detail));
    }
}
