"""테스트는 진짜 AI 와 진짜 Langfuse 를 부르지 않는다(가짜 LLM, 키 비움)."""
import os

os.environ.update({"LLM_PROVIDER": "fake", "LLM_API_KEY": "", "TEAM_PASSWORD": "test-pw", "ENV": "test",
                   "LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": "", "DAILY_LIMIT": "1000"})
