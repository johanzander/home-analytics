#!/bin/bash
# Run linting and code quality checks

set -e

echo "🔍 Running code quality checks..."

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Format code with Black
echo "📝 Formatting code with Black..."
black backend/ frontend/src/

# Lint with Ruff
echo "🔎 Linting with Ruff..."
ruff check backend/ --fix

# Type check with MyPy
echo "🔍 Type checking with MyPy..."
mypy backend/

# Lint markdown files
echo "📝 Linting markdown files..."
npx markdownlint "README.md" "*.md" "!reference/**" "!node_modules/**" "!venv/**"

echo "✅ All checks passed!"