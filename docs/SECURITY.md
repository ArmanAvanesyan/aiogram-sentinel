# Security Policy

## Supported Versions

We provide security updates for the following versions of aiogram-sentinel:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

**IMPORTANT**: If you believe you have found a security vulnerability, please **DO NOT** open a public issue.

### Private Reporting

Please report security vulnerabilities privately to:

- **Email**: security@aiogram-sentinel.dev
- **GitHub Security Advisories**: [Create a private security advisory](https://github.com/ArmanAvanesyan/aiogram-sentinel/security/advisories/new)

### What to Include

When reporting a vulnerability, please include:

1. **Description**: Clear description of the vulnerability
2. **Steps to Reproduce**: Detailed steps to reproduce the issue
3. **Impact**: Potential impact and severity
4. **Environment**: Version information, OS, Python version
5. **Proof of Concept**: If possible, provide a minimal PoC (without exploiting it)

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Resolution**: Within 90 days (unless otherwise agreed)

## Security Best Practices

### For Users

#### 1. Keep Dependencies Updated

```bash
# Regularly update aiogram-sentinel
pip install --upgrade aiogram-sentinel

# Check for known vulnerabilities
pip-audit
```

#### 2. Secure Redis Connections

```python
# Use SSL/TLS for Redis connections
storage = RedisStorage(
    url="rediss://your-redis-server:6380",  # Note: rediss:// for SSL
    password="strong_password",
    ssl_cert_reqs="required",
)
```

#### 3. Environment Variables

```bash
# Use environment variables for sensitive data
export REDIS_PASSWORD="your_secure_password"
export BOT_TOKEN="your_bot_token"
```

#### 4. Network Security

- Use firewalls to restrict access to Redis
- Run Redis on private networks when possible
- Use VPN or SSH tunnels for remote access

#### 5. Access Control

```python
# Implement proper user access controls
@dp.message(Command("admin"))
async def admin_command(message: Message):
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Access denied")
        return
    
    # Admin functionality
    await message.answer("Admin panel")
```

### For Developers

#### 1. Input Validation

```python
# Always validate user input
@dp.message()
async def handle_message(message: Message):
    # Validate message content
    if not message.text or len(message.text) > 1000:
        await message.answer("Invalid message")
        return
    
    # Process message
    await message.answer("Message processed")
```

#### 2. Rate Limiting

```python
# Implement appropriate rate limits
config = SentinelConfig(
    throttling_default_max=5,      # Reasonable limit
    throttling_default_per_seconds=60,
)
```

#### 3. Error Handling

```python
# Don't expose sensitive information in errors
try:
    await process_message(message)
except Exception as e:
    # Log the full error internally
    logging.error(f"Error processing message: {e}")
    
    # Return generic error to user
    await message.answer("An error occurred. Please try again.")
```

#### 4. Logging Security

```python
# Avoid logging sensitive data
import logging

# Good: Log user ID (not sensitive)
logging.info(f"User {message.from_user.id} sent a message")

# Bad: Log message content (might be sensitive)
logging.info(f"User sent: {message.text}")
```

## Security Features

### 1. Rate Limiting

aiogram-sentinel provides built-in rate limiting to prevent:

- **Spam attacks**: Excessive message sending
- **DDoS attacks**: Overwhelming the bot with requests
- **Resource exhaustion**: Preventing system overload

### 2. Rate Limiting Protection

```python
# Rate limiting provides protection against spam and abuse
config = SentinelConfig(
    throttling_default_max=5,      # Limit messages per window
    throttling_default_per_seconds=60,  # Time window
)
```

### 3. Input Sanitization

```python
# Sanitize user input
from aiogram_sentinel.utils.keys import fingerprint

# Create safe fingerprints
safe_fingerprint = fingerprint(message.text)
```

### 4. Storage Security

- **Memory storage**: Data is not persisted
- **Redis storage**: Supports authentication and SSL
- **Key isolation**: User data is properly isolated

## Security Considerations

### 1. Data Privacy

- User data is stored locally or in your Redis instance
- No data is sent to external services
- You control all data storage and retention

### 2. Network Security

- Use HTTPS for webhook endpoints
- Encrypt Redis connections in production
- Implement proper firewall rules

### 3. Access Control

- Implement proper user authentication
- Use role-based access control
- Monitor and log access attempts

### 4. Monitoring

```python
# Monitor for suspicious activity
async def security_monitor(user_id: int, action: str):
    # Log security events
    logging.warning(f"Security event: User {user_id} performed {action}")
    
# Implement automatic rate limiting for repeated violations
if action == "rate_limit_exceeded":
    # Rate limit user after multiple violations
    pass
```

## Compliance

### GDPR Compliance

- User data is stored locally
- You control data retention policies
- Users can request data deletion

### Data Retention

```python
# Implement data retention policies
async def cleanup_old_data():
    # Remove old rate limit data
    await sentinel.rate_limiter_backend.cleanup_expired()
    
    # Remove old debounce data
    await sentinel.debounce_backend.cleanup_expired()
```

## Security Updates

### Automatic Updates

We recommend enabling automatic security updates:

```bash
# Use pip-tools for dependency management
pip-compile requirements.in
pip-sync requirements.txt
```

### Monitoring Security Advisories

- Subscribe to GitHub security advisories
- Monitor Python security announcements
- Follow aiogram security updates

## Incident Response

### 1. Detection

- Monitor logs for suspicious activity
- Set up alerts for rate limit violations
- Track failed authentication attempts

### 2. Response

```python
# Automatic response to security incidents
async def handle_security_incident(user_id: int, incident_type: str):
    if incident_type == "rate_limit_exceeded":
        # Log incident
        logging.warning(f"Security incident: User {user_id} rate limited")
        
        # Additional security measures can be implemented here
```

### 3. Recovery

- Have backup and recovery procedures
- Test incident response procedures
- Document lessons learned

## Security Checklist

### Before Deployment

- [ ] Update all dependencies
- [ ] Configure secure Redis connection
- [ ] Set up proper rate limits
- [ ] Implement access controls
- [ ] Configure logging
- [ ] Test security features

### Regular Maintenance

- [ ] Monitor security advisories
- [ ] Update dependencies monthly
- [ ] Review access logs
- [ ] Test backup procedures
- [ ] Audit user permissions

## Contact

For security-related questions or concerns:

- **Security Email**: security@aiogram-sentinel.dev
- **General Issues**: [GitHub Issues](https://github.com/ArmanAvanesyan/aiogram-sentinel/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ArmanAvanesyan/aiogram-sentinel/discussions)

## Acknowledgments

We thank the security researchers and community members who help keep aiogram-sentinel secure by responsibly reporting vulnerabilities.

## Changelog

Security-related changes are documented in our [CHANGELOG.md](CHANGELOG.md) and marked with the `[SECURITY]` tag.
