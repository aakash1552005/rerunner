## Summary

Provide a concise summary of the change and the problem it solves.

Closes # (issue number if applicable)

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change fixing an issue)
- [ ] ✨ New feature (non-breaking change adding functionality)
- [ ] 💥 Breaking change (fix or feature causing existing functionality to change)
- [ ] 📝 Documentation update
- [ ] ⚡ Performance optimization
- [ ] 🧪 Test addition or refactor

## Engineering Checklist

- [ ] My code adheres to the project's style guidelines (`ruff check .` & `ruff format --check .` pass)
- [ ] My code passes strict type checking (`mypy src` passes)
- [ ] Architecture layer boundaries remain intact (`lint-imports` passes)
- [ ] I have added tests verifying that my fix or feature works
- [ ] All existing and new tests pass locally (`pytest` passes)
- [ ] I have updated documentation or docstrings where necessary
- [ ] If changing cassette schemas, backward compatibility is preserved or migrated

## Author Readiness

- [ ] I have reviewed the complete diff myself and verified every modified behavior and test claim.
