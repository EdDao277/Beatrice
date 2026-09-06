package com.beatrice.backend.reference;

import java.nio.file.Path;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Explicit local startup option only. The web API never accepts filesystem paths. */
@Component
@ConditionalOnProperty(name="beatrice.reference.import-file")
public class ReferenceImportRunner implements ApplicationRunner {
    private final ReferenceImporter importer; private final String path;
    public ReferenceImportRunner(ReferenceImporter importer,@Value("${beatrice.reference.import-file}") String path) {this.importer=importer;this.path=path;}
    @Override public void run(ApplicationArguments args) throws Exception {
        var report=importer.importFile(Path.of(path));
        System.out.println("CompCraft reference import: " + report);
    }
}
