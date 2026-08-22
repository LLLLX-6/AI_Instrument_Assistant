import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { resolve } from "node:path";


export type JsonSchemaDocument = Record<string, unknown>;

export interface LoadedSchema {
  readonly path: string;
  readonly id: string;
  readonly document: JsonSchemaDocument;
}

export class SchemaFileNotFoundError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SchemaFileNotFoundError";
  }
}

export class SchemaDefinitionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SchemaDefinitionError";
  }
}

export class SchemaReferenceError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "SchemaReferenceError";
  }
}

export class SchemaLoader {
  static loadDirectory(protocolRoot: string): readonly LoadedSchema[] {
    const root = resolve(protocolRoot);
    if (!existsSync(root) || !statSync(root).isDirectory()) {
      throw new SchemaFileNotFoundError(`Schema directory does not exist: ${root}`);
    }

    const paths = readdirSync(root, { recursive: true, withFileTypes: true })
      .filter((entry) => entry.isFile() && entry.name.endsWith(".schema.json"))
      .map((entry) => resolve(entry.parentPath, entry.name))
      .sort();
    if (paths.length === 0) {
      throw new SchemaFileNotFoundError(`No JSON Schema files found under: ${root}`);
    }
    return SchemaLoader.loadFiles(paths);
  }

  static loadFiles(paths: readonly string[]): readonly LoadedSchema[] {
    if (paths.length === 0) {
      throw new SchemaFileNotFoundError("No JSON Schema files were supplied");
    }

    const identifiers = new Map<string, string>();
    return paths.map((suppliedPath) => {
      const path = resolve(suppliedPath);
      if (!existsSync(path) || !statSync(path).isFile()) {
        throw new SchemaFileNotFoundError(`Schema file does not exist: ${path}`);
      }

      let document: unknown;
      try {
        document = JSON.parse(readFileSync(path, "utf8"));
      } catch (error) {
        throw new SchemaDefinitionError(`Cannot read JSON Schema document ${path}: ${error}`);
      }
      if (typeof document !== "object" || document === null || Array.isArray(document)) {
        throw new SchemaDefinitionError(`Schema root must be an object: ${path}`);
      }

      const schema = document as JsonSchemaDocument;
      const identifier = schema.$id;
      if (typeof identifier !== "string" || identifier.length === 0) {
        throw new SchemaDefinitionError(`Schema has no non-empty $id: ${path}`);
      }
      const previousPath = identifiers.get(identifier);
      if (previousPath !== undefined) {
        throw new SchemaDefinitionError(
          `Duplicate schema $id ${JSON.stringify(identifier)}: ${previousPath} and ${path}`,
        );
      }
      identifiers.set(identifier, path);

      return { path, id: identifier, document: schema };
    });
  }
}
