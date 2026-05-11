#!/usr/bin/env python3
"""Test OpenSpace skill discovery."""

from pathlib import Path
from reviewstem.openspace_integration import ReviewStemSkillEngine
from reviewstem.llm_client import LLMClient
from reviewstem.config import ReviewStemConfig

config = ReviewStemConfig(
    model='gpt-4o-mini',
    max_iterations=1,
    target_score=0.9,
    temperature=0,
    diff_limit=12000,
    repo_map_max_files=150,
    file_read_limit=8000
)

llm = LLMClient(config)
engine = ReviewStemSkillEngine([Path('skills/openspace')], llm)

print('OpenSpace initialized successfully')
print(f'Found {len(engine.registry.list_skills())} skills')

for skill in engine.registry.list_skills():
    print(f'  - {skill.name}: {skill.description[:60]}...')
