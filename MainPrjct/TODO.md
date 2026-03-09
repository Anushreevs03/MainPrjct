# Real-Time Student Monitoring System - Implementation Plan

## Task Requirements:
1. Backend API to store and update: student_name, join_timestamp, active_app, app_usage_duration, violation_events
2. Use WebSocket to push updates instantly to frontend
3. Sort students by most recent join time
4. Automatically remove student from list when disconnected
5. Highlight violation students with red border animation

## Current Status Analysis:
- **Backend (app.py)**: Has SQLite database with classes, students, activity_events, student_sessions tables. WebSocket support exists with handlers.
- **Dashboard (templates/dashboard.html)**: React-based, shows students sorted by join time, has some violation styling.
- **Index (templates/index.html)**: Teacher/student screens with activity tracking.

## Implementation Plan:

### Phase 1: Backend Enhancements (app.py)
- [ ] 1.1 Add WebSocket events for student disconnect handling
- [ ] 1.2 Create API endpoint for real-time student list with all required fields
- [ ] 1.3 Implement proper session management for active students
- [ ] 1.4 Add socket emission for student list updates

### Phase 2: Frontend Dashboard Enhancements (templates/dashboard.html)
- [ ] 2.1 Improve WebSocket handling for real-time updates
- [ ] 2.2 Add student disconnect handling to remove from list
- [ ] 2.3 Add red border animation for violation students
- [ ] 2.4 Implement proper sorting by join time
- [ ] 2.5 Enhance student card to show all required fields

### Phase 3: Testing & Verification
- [ ] 3.1 Test WebSocket connection
- [ ] 3.2 Test student join/disconnect flow
- [ ] 3.3 Verify violation highlighting
- [ ] 3.4 Test real-time updates

## Files to be Modified:
1. app.py - Backend enhancements
2. templates/dashboard.html - Frontend enhancements
