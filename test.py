#!/usr/bin/env python3

import anthropic
import os
from dotenv import load_dotenv


load_dotenv()

print('pkg_ok', anthropic.__version__)

r = anthropic.Anthropic().messages.create(
    model="claude-sonnet-4-6",
    max_tokens=10,
    messages=[{
        'role': 'user',
        'content': 'hi'
    }]
)

print('ok', r.model)
