# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-04-27

### Added

- Initial release
- TTL policy with absolute and sliding modes
- LRU policy
- LFU policy
- Composite orchestrator to combine multiple policies
- `@snap` decorator for function caching
- Template key support with `key="user-{user_id}"` format
- Built-in hit/miss/eviction metrics
- Thread-safe InMemoryStorage
- Hexagonal architecture — custom policies, storages, metrics supported
