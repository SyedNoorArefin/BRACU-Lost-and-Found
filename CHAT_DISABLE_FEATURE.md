# Chat Disable Feature

## Overview

The chat disable feature automatically disables a user's chat functionality when they receive 2 or more reports from other users. This helps maintain a safe and respectful community environment.

## How It Works

### Trigger Conditions
- **2 Reports**: Chat is disabled for 7 days
- **5+ Reports**: Full account suspension for 30 days (includes chat disable)

### Suspension Types
1. **Chat Ban (`chat_ban`)**: User cannot send messages but can still post items
2. **Full Suspension (`full_suspension`)**: User cannot post items or send messages

## Implementation Details

### Backend Changes

#### 1. Updated Reporting System (`app.py`)
- Modified the report handling logic in `/report_user/<int:user_id>` route
- When a user receives 2 reports, a `chat_ban` suspension is created
- Duration: 7 days for chat ban, 30 days for full suspension

#### 2. New API Endpoints
- `/api/chat/status` - Check if user's chat is enabled/disabled
- Enhanced `/api/chat/<int:conversation_id>/messages` - Returns detailed error messages for suspended users

#### 3. Helper Functions
- `can_user_chat(user_id)` - Checks if user can send messages
- `get_user_report_count(user_id)` - Gets current active report count

### Frontend Changes

#### 1. Chat Interface (`templates/chat.html`)
- Added `checkChatStatus()` function to check chat status on page load
- Disables chat input and shows warning when chat is suspended
- Enhanced `sendMessage()` function to check status before sending

#### 2. Home Page (`templates/home.html`)
- Added `checkChatStatusAndUpdateUI()` function
- Disables chat buttons and shows warning banner when chat is suspended
- Enhanced `startChatFromItem()` to check status before starting conversations

#### 3. Profile Page (`templates/profile.html`)
- Updated suspension display to show chat-specific warnings
- Added visual indicators for chat suspensions with icons

## User Experience

### For Suspended Users
1. **Chat Interface**: Input is disabled with warning message
2. **Home Page**: Chat buttons are disabled and show "Chat Disabled"
3. **Profile Page**: Clear indication of suspension status and duration
4. **API Responses**: Detailed error messages with remaining time

### For Other Users
- Can still view messages from suspended users
- Cannot receive new messages from suspended users
- No impact on their own chat functionality

## Database Schema

### UserSuspension Model
```python
class UserSuspension(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    suspension_type = db.Column(db.String(20), nullable=False)  # 'chat_ban', 'full_suspension'
    reason = db.Column(db.String(500), nullable=False)
    report_count = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    end_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
```

## API Responses

### Chat Status Check (`/api/chat/status`)
```json
{
    "chat_enabled": false,
    "suspension_type": "chat_ban",
    "reason": "Chat disabled due to multiple reports (Total: 2)",
    "remaining_time": "6d 12h",
    "end_date": "2024-01-15T10:30:00",
    "message": "Your chat has been disabled for 6d 12h due to multiple reports."
}
```

### Send Message Error (403)
```json
{
    "error": "Your chat has been disabled for 6d 12h due to multiple reports. You can still post items but cannot send messages.",
    "suspension_type": "chat_ban",
    "remaining_time": "6d 12h"
}
```

## Testing

### Manual Testing
1. Create two test users
2. Report user 2 once (should not trigger suspension)
3. Report user 2 again (should trigger chat disable)
4. Verify chat is disabled in UI
5. Try to send messages (should fail)
6. Check profile page shows suspension

### Automated Testing
Run the test script:
```bash
python test_chat_disable.py
```

## Configuration

### Suspension Durations
- Chat ban: 7 days (configurable in `app.py`)
- Full suspension: 30 days (configurable in `app.py`)

### Report Thresholds
- Chat disable: 2 reports
- Full suspension: 5 reports

## Security Considerations

1. **Report Validation**: Only authenticated users can report others
2. **Self-Reporting Prevention**: Users cannot report themselves
3. **Duplicate Report Prevention**: Users cannot report the same person for the same item multiple times
4. **Suspension Persistence**: Suspensions are stored in database and survive server restarts

## Future Enhancements

1. **Admin Panel**: Interface for managing suspensions
2. **Appeal System**: Allow users to appeal suspensions
3. **Graduated Penalties**: Different suspension durations based on report severity
4. **Automatic Review**: AI-powered review of reports before applying suspensions
5. **Notification System**: Email notifications for suspension events

## Troubleshooting

### Common Issues
1. **Chat not disabled after 2 reports**: Check database for active suspensions
2. **UI not updating**: Clear browser cache and refresh page
3. **API errors**: Verify user authentication and session

### Debug Commands
```python
# Check user's suspension status
from app import UserSuspension, User
user = User.query.get(user_id)
suspensions = UserSuspension.query.filter_by(user_id=user_id, is_active=True).all()

# Check report count
from app import Report
report_count = Report.query.filter_by(reported_user_id=user_id, status='pending').count()
```

## Files Modified

1. `app.py` - Backend logic and API endpoints
2. `templates/chat.html` - Chat interface updates
3. `templates/home.html` - Home page chat button handling
4. `templates/profile.html` - Profile suspension display
5. `test_chat_disable.py` - Test script (new file)
6. `CHAT_DISABLE_FEATURE.md` - This documentation (new file)
