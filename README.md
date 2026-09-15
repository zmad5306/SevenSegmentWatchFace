# Watch faces

Wear OS watch faces built with [Watch Face Format](https://developer.android.com/training/wearables/wff). Each face is a Gradle module in its own directory. The modules share the Gradle wrapper, version catalog, and root build settings.

| Face                             | Module           |
|----------------------------------|------------------|
| [Seven Segment](seven-segment/)  | `:seven-segment` |

Run commands from the repository root, for example:

```bash
./gradlew :seven-segment:assembleDebug
```

## Adding a face
1. Create a directory with its own `build.gradle.kts`, `src/main`, and any generator tooling. Copy `seven-segment/` as a starting point.
2. Give it a unique `namespace` and `applicationId`.
3. Add `include(":<dir>")` to `settings.gradle.kts` and a row to the table above.
