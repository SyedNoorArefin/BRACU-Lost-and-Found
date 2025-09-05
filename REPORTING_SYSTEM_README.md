# 🚨 Reporting System for Scams and Harassment

## Overview
This system allows users to report other users or specific items for scams and harassment. The system automatically applies suspensions based on the number of reports received.

## 🎯 Features

### 1. User Reporting
- Report users directly for scams or harassment
- Can be related to specific items or general behavior
- Prevents duplicate reports from the same user



### 3. Automatic Suspension System
- **2+ reports**: 5-day posting and chat ban
- **5+ reports**: 30-day full account suspension
- Suspensions are applied automatically when thresholds are reached

### 4. Notification System
- Users receive notifications when reported
- Suspension notifications with clear explanations
- Report status updates

## 🗄️ Database Models

### Report Model
```python
class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    reported_user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    item_id = db.Column(db.Integer, db.ForeignKey('lost_item.id'), nullable=True)
    report_type = db.Column(db.String(20))  # 'scam' or 'harassment'
    reason = db.Column(db.String(500))
    evidence = db.Column(db.String(1000), nullable=True)
    status = db.Column(db.String(20), default='pending')
    admin_notes = db.Column(db.String(1000), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
```

### UserSuspension Model
```python
class UserSuspension(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    suspension_type = db.Column(db.String(20))  # 'posting_ban', 'chat_ban', 'full_suspension'
    reason = db.Column(db.String(500))
    report_count = db.Column(db.Integer)
    start_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    end_date = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
```

## 🛣️ Routes

### Report User
- **URL**: `/report_user/<int:user_id>`
- **Methods**: GET, POST
- **Description**: Report a specific user for scams or harassment



## 🔧 Helper Functions

### Suspension Checks
```python
def is_user_suspended(user_id, suspension_type='full_suspension')
def can_user_post(user_id)
def can_user_chat(user_id)
def get_user_report_count(user_id)
```

### Usage
- These functions are automatically called in relevant routes
- Posting and chat routes check suspension status before allowing actions
- Profile page displays current suspension status

## 🎨 User Interface

### Report Buttons
- **Report Item**: Red outline button with flag icon
- **Report User**: Yellow outline button with user-slash icon
- Only visible to non-owners of items
- Requires user authentication

### Profile Display
- Shows current report count
- Displays active suspensions with end dates
- Lists recent reports received
- Color-coded alerts based on report count

## 📱 Templates

### report_user.html
- Form to report users
- Shows user information being reported
- Includes report type selection and reason fields



### profile.html (Updated)
- New section showing report count and suspension status
- Displays active suspensions and recent reports
- Color-coded status indicators

## 🚫 Suspension Enforcement

### Posting Restrictions
- Users cannot create new lost/found items when suspended
- Edit and delete functions remain available for existing items

### Chat Restrictions
- Users cannot send messages when suspended
- Chat interface shows suspension messages
- Existing conversations remain visible but read-only

### Automatic Lifting
- Suspensions automatically expire based on end dates
- No manual intervention required
- Users can resume normal activities after suspension period

## 🔒 Security Features

### Duplicate Prevention
- Users cannot report the same person for the same item multiple times
- System tracks report history to prevent abuse

### Self-Reporting Prevention
- Users cannot report themselves
- System validates reporter vs. reported user

### Authentication Required
- All reporting functions require user login
- Anonymous reporting not allowed

## 📊 Monitoring and Analytics

### Activity Logging
- All reports are logged in the activity system
- Includes reporter, reported user, and item information
- Tracks report types and reasons

### Report Statistics
- Count of active reports per user
- Suspension history and durations
- Report type distribution

## 🧪 Testing

### Test Script
Run `python test_reporting_system.py` to test basic functionality.

### Manual Testing Steps
1. Start the Flask app: `python app.py`
2. Login with a user account
3. Browse items and test report buttons
4. Submit test reports
5. Check profile page for status updates
6. Verify suspension enforcement

## 🚀 Future Enhancements

### Admin Panel
- Review and manage reports
- Override automatic suspensions
- Add admin notes and resolutions

### Appeal System
- Allow users to appeal suspensions
- Provide evidence for reconsideration
- Admin review process

### Advanced Analytics
- Report trend analysis
- User behavior patterns
- Community safety metrics

## 📝 Notes

- The system is designed to be self-regulating
- Suspensions are applied automatically based on report thresholds
- All actions are logged for transparency and audit purposes
- The system prioritizes community safety while maintaining user rights

## 🆘 Support

For issues or questions about the reporting system:
1. Check the activity logs for detailed information
2. Review the database for report and suspension records
3. Verify user authentication and permissions
4. Check for any error messages in the Flask application logs
