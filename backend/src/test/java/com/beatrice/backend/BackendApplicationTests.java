package com.beatrice.backend;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@org.springframework.context.annotation.Import(com.beatrice.backend.TestDatabase.class)
class BackendApplicationTests {

	@Test
	void contextLoads() {
	}

}
