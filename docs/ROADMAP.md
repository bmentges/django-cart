# django-cart Development Roadmap

**Current Version:** 3.0.0  
**Last Updated:** March 2026  
**Repository:** https://github.com/bmentges/django-cart

---

## Future Considerations

The following features are marked for future consideration and are not yet scheduled:

| Feature | Priority | Notes |
|---------|----------|-------|
| Multi-currency support | Low | Complex currency conversion |
| Gift wrapping options | Low | Requires order customization |
| Cart notes field | Medium | Simple addition |
| Saved carts | Medium | User preference feature |
| Cart sharing | Low | Social commerce feature |
| Abandoned cart emails | Medium | Requires user identification |
| Cart expiration | Medium | Background task integration |
| Async cart operations | Low | Django async view support |

### Potential Deprecations

| Feature | Reason | Timeline |
|---------|--------|----------|
| `Cart._new()` private method | Internal API may change | v4.0.0 |
| Session key format | May need to change for scalability | v4.0.0 |

---

## Version Compatibility

| Version | Python | Django |
|---------|--------|--------|
| v3.0.0 | 3.10+ | 4.2+ |

---

*Roadmap maintained by project maintainers*  
*Last updated: March 2026*
