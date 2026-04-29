# Contributing to MindWell

Thank you for your interest in contributing! This document provides guidelines and instructions.

## 🚀 Getting Started

### 1. Fork and Clone
```bash
git clone https://github.com/yourusername/mindwell-ai.git
cd mindwell-ai
```

### 2. Create Feature Branch
```bash
git checkout -b feature/your-feature-name
# or for bugs:
git checkout -b fix/bug-description
```

### 3. Set Up Development Environment
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Create .env File
```bash
cp .env.example .env
# Edit .env with your PostgreSQL and LLM credentials
```

## 💻 Development Guidelines

### Code Style
- Follow PEP 8
- Use meaningful variable names
- Maximum line length: 100 characters
- Type hints for functions

### Commit Messages
```
feat: Add new feature
fix: Fix a bug
docs: Update documentation
test: Add tests
refactor: Code refactoring
style: Code style changes
perf: Performance improvements

Example:
feat: Add voice input for chat messages
fix: Resolve memory extraction issue
```

### Testing
- Write tests for new features
- Run tests before committing:
```bash
pytest tests/ -v
```

## 📝 Pull Request Process

1. Update your local branch
```bash
git pull origin main
```

2. Push your changes
```bash
git push origin feature/your-feature-name
```

3. Create Pull Request with:
   - Clear title
   - Description of changes
   - Related issue numbers
   - Testing instructions

## 🔐 Security

- Never commit `.env` files
- Don't hardcode credentials
- Test for SQL injection vulnerabilities
- Validate all user inputs

## 🐛 Reporting Issues

When reporting bugs, include:
- Clear description of the issue
- Steps to reproduce
- Expected vs actual behavior
- System information (Python version, OS, etc.)
- Error logs if applicable

## ✅ Code Review Checklist

- [ ] Code follows style guide
- [ ] Self-review completed
- [ ] Comments added for clarity
- [ ] Tests written/updated
- [ ] All tests passing
- [ ] No hardcoded credentials
- [ ] Documentation updated

## 📚 Resources

- [README.md](README.md) - Project overview
- [Database Schema](docs/README.md) - Database documentation
- [Streamlit Docs](https://docs.streamlit.io)
- [LangChain Docs](https://python.langchain.com)

---

Thank you for contributing to MindWell! 🧠💚
