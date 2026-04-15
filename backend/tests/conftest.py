"""
Pytest configuration and shared fixtures.
Adds the backend/ directory to sys.path so modules can be imported directly.
"""
import sys
import os

# Allow "from vector_store import …" etc. without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
