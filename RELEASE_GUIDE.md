# Release Guide for pytest-html-reporter 0.3.0

## The Fix
Version 0.3.0 fixes the compatibility issue with pytest 9.x where:
- **Error:** `AttributeError: 'TerminalReporter' object has no attribute '_sessionstarttime'`
- **Root Cause:** Older versions accessed pytest's internal `_sessionstarttime` attribute
- **Solution:** Now uses self-managed session timing (`self._sessionstarttime`)

## Quick Install (For Immediate Use)

Users experiencing this issue can install directly from the 0.3.0 branch:

```bash
pip uninstall pytest-html-reporter
pip install git+https://github.com/prashanth-sams/pytest-html-reporter.git@0.3.0
```

## Publishing to PyPI

### Prerequisites
```bash
pip install --upgrade build twine
```

### Steps

1. **Clean old builds**
   ```bash
   rm -rf build/ dist/ *.egg-info
   ```

2. **Build the distribution**
   ```bash
   python -m build
   ```

3. **Check the distribution**
   ```bash
   twine check dist/*
   ```

4. **Upload to Test PyPI (optional)**
   ```bash
   twine upload --repository testpypi dist/*
   ```

5. **Upload to PyPI**
   ```bash
   twine upload dist/*
   ```

6. **Create a Git Tag**
   ```bash
   git tag -a v0.3.0 -m "Release version 0.3.0 - pytest 9.x compatibility"
   git push origin v0.3.0
   ```

7. **Create GitHub Release**
   - Go to https://github.com/prashanth-sams/pytest-html-reporter/releases/new
   - Tag: v0.3.0
   - Title: Release 0.3.0 - pytest 9.x Compatibility
   - Description: See CHANGELOG.txt

## Testing Before Release

```bash
# Install in development mode
pip install -e .

# Run the test suite
pytest tests/

# Test with a sample project
cd /path/to/test/project
pytest --html-report=./report
```

## Verifying the Fix

After installation, users should see:
- ✅ Tests run successfully
- ✅ HTML report generated without errors
- ✅ No `AttributeError` related to `_sessionstarttime`

## Notes
- Current version in setup.py: 0.3.0 ✓
- CHANGELOG.txt updated: ✓
- Compatible with pytest 9.x: ✓
