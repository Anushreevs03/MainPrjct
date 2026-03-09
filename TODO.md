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

### Phase 1: Backend Enhancements (app.py) - ✅ COMPLETED
- [x] 1.1 Add WebSocket events for student disconnect handling
- [x] 1.2 Create API endpoint for real-time student list with all required fields
- [x] 1.3 Implement proper session management for active students
- [x] 1.4 Add socket emission for student list updates

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

## Files Modified:
1. app.py - Backend enhancements ✅ COMPLETED
2. templates/dashboard.html - Frontend enhancements (pending)

## Changes Made to app.py:

### Added Database Tables:
- `activity_events` - Stores all student activity (app_switch, tab_switch, window_blur, idle, etc.)
- `student_sessions` - Tracks active sessions with start/end times

### Added API Endpoints:
- `/student_activity` - Records activity and increments violations
- `/leave_class` - Handles student leaving with session update
- `/teacher_notifications/<class_id>` - Real-time notifications for teacher
- `/get_class/<class_code>` - Gets class information
- `/class_activities/<class_code>` - Gets all activities for a class
- `/api/dashboard/<class_id>` - Dashboard data with all student details
- `/api/student/app` - Updates current app being used
- `/api/classes` - Gets all classes with active student count

### Added WebSocket Events:
- `join_classroom` - Student joins a classroom
- `student_joined` - Broadcast when student joins
- `student_left` - Broadcast when student leaves
- `violation_detected` - Broadcast violation alerts
- `app_changed` - Broadcast app change updates
