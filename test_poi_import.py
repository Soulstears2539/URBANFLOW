#!/usr/bin/env python
"""Test script to check if POI blueprint imports correctly."""

try:
    from backend.blueprints import poi
    print(f"✓ POI blueprint imported successfully")
    print(f"  Blueprint object: {poi.bp}")
    print(f"  URL prefix: {poi.bp.url_prefix}")
    
    # List routes
    print(f"  Routes registered on blueprint:")
    for rule in poi.bp.deferred_functions:
        print(f"    - {rule}")
        
except ImportError as e:
    print(f"✗ ImportError: {e}")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
