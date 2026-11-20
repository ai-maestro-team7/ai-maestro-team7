"""A 입구. 백엔드가 부르는 것은 둘뿐이다 (Requirement 1 기준 2).
- `rest_handler.handle(event, deps, user_id)`: `/api/v1/mentoring/*` (BE-1)
- `task_handler.handle(event, deps)`: 비동기 작업 이벤트 `{"mentoringTask": {...}}` (BE-2)
"""
