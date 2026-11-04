"""Task logic shared by the desktop app and the Android app (no Qt, no Android imports).

Platform code (ui/ for Windows, android/ for the phone) only adapts these functions to its
own UI and storage; the rules and messages live here so both apps behave the same.
"""
