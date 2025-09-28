# Frequently Asked Questions

Common questions and answers about aiogram-sentinel.

## Installation & Setup

### Q: How do I install aiogram-sentinel?

**A**: Install using pip:

```bash
pip install aiogram-sentinel
```

Or using uv (recommended):

```bash
uv add aiogram-sentinel
```

### Q: What Python versions are supported?

**A**: aiogram-sentinel supports Python 3.10 and higher.

### Q: Do I need Redis to use aiogram-sentinel?

**A**: No, Redis is optional. aiogram-sentinel works with in-memory storage by default, which is perfect for development and small bots. Redis is recommended for production use.

### Q: How do I check if aiogram-sentinel is installed correctly?

**A**: Test the installation:

```python
from aiogram_sentinel import Sentinel
print("aiogram-sentinel installed successfully!")
```

## Configuration

For detailed configuration information, see the [Configuration Guide](configuration.md).

### Q: What's the difference between rate limiting and debouncing?

**A**: 
- **Rate limiting**: Controls how many messages a user can send within a time window (e.g., 5 messages per minute)
- **Debouncing**: Prevents processing duplicate messages within a short time period (e.g., ignore repeated messages for 3 seconds)

See the [Configuration Guide](configuration.md) for detailed examples and options.

## Usage

For detailed usage examples, see the [Tutorials](tutorials/) and [API Reference](api/).

### Q: How do I block a user programmatically?

**A**: Use the blocklist backend. See the [API Reference](api/storage.md) for detailed examples.

### Q: How do I check if a user is rate limited?

**A**: Check the rate limiter. See the [API Reference](api/storage.md) for detailed examples.

### Q: How do I get user information?

**A**: Use the user repository. See the [API Reference](api/storage.md) for detailed examples.

### Q: How do I handle rate limit exceeded events?

**A**: Use the on_rate_limited hook. See the [Configuration Guide](configuration.md) for detailed examples.

## Storage

For detailed storage information, see the [API Reference](api/storage.md) and [Redis Storage Tutorial](tutorials/redis-storage.md).

### Q: What's the difference between memory and Redis storage?

**A**: 
- **Memory storage**: Fast, but data is lost when the bot restarts
- **Redis storage**: Persistent, shared across multiple bot instances, but requires Redis server

See the [Performance Guide](performance.md) for detailed comparisons.

## Performance

For detailed performance information, see the [Performance Guide](performance.md).

### Q: How many users can aiogram-sentinel handle?

**A**: This depends on your hardware and configuration. See the [Performance Guide](performance.md) for detailed benchmarks and scaling information.

### Q: How much memory does aiogram-sentinel use?

**A**: See the [Performance Guide](performance.md) for detailed memory usage analysis.

### Q: How do I optimize performance?

**A**: See the [Performance Guide](performance.md) for optimization guidelines and best practices.

## Troubleshooting

For detailed troubleshooting information, see the [Troubleshooting Guide](troubleshooting.md).

### Q: My bot is not responding to messages

**A**: See the [Troubleshooting Guide](troubleshooting.md) for step-by-step diagnosis.

### Q: Users are getting blocked unexpectedly

**A**: See the [Troubleshooting Guide](troubleshooting.md) for rate limiting issues.

### Q: Redis connection errors

**A**: See the [Troubleshooting Guide](troubleshooting.md) for Redis connection issues.

### Q: How do I debug middleware issues?

**A**: See the [Troubleshooting Guide](troubleshooting.md) for debugging techniques.

## Integration

For integration examples, see the [Quickstart Guide](quickstart.md) and [Tutorials](tutorials/).

### Q: How do I integrate with existing aiogram bots?

**A**: See the [Quickstart Guide](quickstart.md) for step-by-step integration.

### Q: Can I use aiogram-sentinel with other middleware?

**A**: Yes, aiogram-sentinel works with other aiogram middleware. See the [Tutorials](tutorials/) for examples.

### Q: How do I use aiogram-sentinel with webhooks?

**A**: See the [Tutorials](tutorials/) for webhook integration examples.

## Advanced Usage

For advanced usage examples, see the [Tutorials](tutorials/) and [API Reference](api/).

### Q: How do I create custom storage backends?

**A**: See the [API Reference](api/storage.md) for protocol definitions and examples.

### Q: How do I implement custom middleware?

**A**: See the [Tutorials](tutorials/) for custom middleware examples.

### Q: How do I handle different user types?

**A**: See the [Tutorials](tutorials/) for user type handling examples.

## Security

For security information, see the [Security Policy](../SECURITY.md).

### Q: Is aiogram-sentinel secure?

**A**: Yes, aiogram-sentinel is designed with security in mind. See the [Security Policy](../SECURITY.md) for details.

### Q: How do I secure Redis connections?

**A**: See the [Security Policy](../SECURITY.md) for Redis security guidelines.

### Q: Can I audit user actions?

**A**: See the [Configuration Guide](configuration.md) for audit hook examples.

## Versioning & Updates

### Q: How do I update aiogram-sentinel?

**A**: Update using pip: `pip install --upgrade aiogram-sentinel`

### Q: What's the versioning policy?

**A**: aiogram-sentinel follows semantic versioning. See the [Changelog](../CHANGELOG.md) for details.

### Q: How do I check the current version?

**A**: Check the installed version: `import aiogram_sentinel; print(aiogram_sentinel.__version__)`

## Support

### Q: Where can I get help?

**A**: 
- **Documentation**: [Read the full docs](https://github.com/ArmanAvanesyan/aiogram-sentinel/tree/main/docs)
- **GitHub Issues**: [Report bugs](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues)
- **Discussions**: [Ask questions](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions)

### Q: How do I report a bug?

**A**: Open a GitHub issue with version information, error details, and steps to reproduce.

### Q: Can I contribute to the project?

**A**: Yes! See [CONTRIBUTING.md](../CONTRIBUTING.md) for details.
