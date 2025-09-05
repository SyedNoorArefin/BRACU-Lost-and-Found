# Password Reset Verification System

## Overview

The password reset functionality now includes email verification, similar to the signup process. This adds an extra layer of security to ensure that only users with access to the registered email address can reset their password.

## How It Works

### 1. Request Password Reset
- User visits `/forgot_password`
- Enters their email address
- System checks if the email exists in the database
- If email exists, a 6-digit verification code is generated and sent via email
- User is redirected to `/verify_password_reset`

### 2. Email Verification
- User receives a 6-digit verification code via email
- User enters the code on the verification page
- System validates the code and checks if it's expired (10-minute expiration)
- If valid, user is redirected to `/reset_password_with_code`

### 3. Set New Password
- User enters their new password and confirms it
- System updates the user's password in the database
- User is redirected to login page

## New Routes Added

### `/verify_password_reset` (GET, POST)
- **GET**: Displays the verification code entry form
- **POST**: Validates the verification code and redirects to password reset if valid

### `/reset_password_with_code` (GET, POST)
- **GET**: Displays the new password entry form (only accessible after verification)
- **POST**: Updates the user's password in the database

### `/resend_password_reset_verification` (POST)
- Resends a new verification code to the user's email
- Useful if the original code expires or is not received

## New Templates

### `templates/verify_password_reset.html`
- Modern, responsive design matching the application's style
- Form for entering the 6-digit verification code
- Resend code functionality
- Bootstrap styling with Font Awesome icons

### `templates/reset_password_with_code.html`
- Form for entering new password and confirmation
- Only accessible after successful email verification
- Consistent styling with other authentication pages

## Security Features

1. **Time-limited codes**: Verification codes expire after 10 minutes
2. **Single-use codes**: Each code can only be used once
3. **Email verification**: Only users with access to the registered email can reset passwords
4. **Session management**: Proper session handling to prevent unauthorized access
5. **Code cleanup**: Expired codes are automatically cleaned from the database

## Email Configuration

The system uses the same email configuration as the signup verification:

```python
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
```

## Environment Variables Required

To enable email functionality, set these environment variables:

```bash
export MAIL_USERNAME="your-email@gmail.com"
export MAIL_PASSWORD="your-app-password"
```

## Testing

A test script `test_password_reset.py` is included to verify the basic functionality:

```bash
python test_password_reset.py
```

## User Flow

1. User clicks "Forgot Password?" on login page
2. User enters email address
3. System sends verification code via email
4. User enters verification code
5. User enters new password and confirmation
6. Password is updated and user is redirected to login

## Error Handling

- Invalid or expired verification codes show appropriate error messages
- Non-existent email addresses are handled gracefully
- Session management prevents unauthorized access to password reset pages
- Email sending failures are handled with fallback to console output

## Database Changes

The system uses the existing `EmailVerification` model, which stores:
- Email address
- Verification code (6 digits)
- Creation timestamp
- Expiration timestamp
- Usage status (used/unused)

This ensures consistency with the signup verification system and efficient database usage.
