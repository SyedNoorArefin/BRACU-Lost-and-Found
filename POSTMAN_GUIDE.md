# 🚀 Postman API Testing Guide

## **Why Your Previous Postman Tests Failed:**

1. **No API Endpoints**: Your original app only had HTML form-based routes
2. **Session Management**: Postman couldn't maintain sessions properly
3. **Hardcoded Routes**: Profile route was hardcoded to `/profile/1812`
4. **Form vs JSON**: Your app expected form data, not JSON

## **✅ What I Fixed:**

1. **Added API Endpoints**: New `/api/*` routes for Postman testing
2. **JSON Support**: All API endpoints accept and return JSON
3. **Session Management**: Proper session handling for authentication
4. **Dynamic Routes**: Profile route now works for any authenticated user
5. **Error Handling**: Proper HTTP status codes and error messages

## **🔧 New API Endpoints:**

### **Authentication:**
- `POST /api/login` - Login with email/password
- `POST /api/logout` - Logout and clear session

### **User Management:**
- `GET /api/profile` - Get current user's profile
- `PUT /api/profile` - Update current user's profile
- `GET /api/user/<id>` - Get specific user by ID (own profile only)

### **Lost Items:**
- `GET /api/lost-items` - Get all lost items
- `POST /api/lost-items` - Create new lost item

### **Testing:**
- `GET /api/test` - Test if API is working

## **📱 How to Use in Postman:**

### **Step 1: Start Your Flask App**
```bash
python app.py
```

### **Step 2: Test API Connection**
- **Method**: `GET`
- **URL**: `http://127.0.0.1:5000/api/test`
- **Expected Response**: `200 OK` with success message

### **Step 3: Login**
- **Method**: `POST`
- **URL**: `http://127.0.0.1:5000/api/login`
- **Headers**: `Content-Type: application/json`
- **Body** (raw JSON):
```json
{
    "email": "your_email@example.com",
    "password": "your_password"
}
```

### **Step 4: Access Protected Endpoints**
After successful login, Postman will automatically include the session cookie. Now you can:

- **Get Profile**: `GET http://127.0.0.1:5000/api/profile`
- **Update Profile**: `PUT http://127.0.0.1:5000/api/profile`
- **Get Lost Items**: `GET http://127.0.0.1:5000/api/lost-items`

### **Step 5: Logout**
- **Method**: `POST`
- **URL**: `http://127.0.0.1:5000/api/logout`

## **🔑 Important Postman Settings:**

### **Cookies & Sessions:**
1. In Postman, go to **Cookies** (bottom right)
2. Make sure cookies are enabled for `127.0.0.1:5000`
3. Postman will automatically handle session cookies

### **Headers:**
- Set `Content-Type: application/json` for POST/PUT requests
- No special headers needed for GET requests

## **📋 Sample Test Data:**

### **Create User (via web interface first):**
1. Go to `http://127.0.0.1:5000/signup` in your browser
2. Create a test account
3. Use those credentials in Postman

### **Test Login Data:**
```json
{
    "email": "test@example.com",
    "password": "testpassword123"
}
```

### **Update Profile Data:**
```json
{
    "first_name": "John",
    "last_name": "Doe",
    "phone": "+1234567890",
    "address": "123 Main St, City, Country"
}
```

### **Create Lost Item Data:**
```json
{
    "name": "Lost Phone",
    "description": "iPhone 13, black case",
    "value": 999.99,
    "location": "University Library"
}
```

## **🚨 Common Issues & Solutions:**

### **Issue: "Authentication required" (401)**
- **Cause**: Not logged in or session expired
- **Solution**: Login first with `/api/login`

### **Issue: "User not found" (404)**
- **Cause**: User doesn't exist in database
- **Solution**: Create user via web interface first

### **Issue: "Access denied" (403)**
- **Cause**: Trying to access another user's data
- **Solution**: Only access your own profile

### **Issue: Connection refused**
- **Cause**: Flask app not running
- **Solution**: Run `python app.py` first

## **✅ Test Your API:**

1. **Start Flask app**: `python app.py`
2. **Test connection**: `GET /api/test`
3. **Login**: `POST /api/login`
4. **Get profile**: `GET /api/profile`
5. **Update profile**: `PUT /api/profile`
6. **Get lost items**: `GET /api/lost-items`
7. **Logout**: `POST /api/logout`

## **🎯 Success Indicators:**

- ✅ `200 OK` responses for successful operations
- ✅ `201 Created` for new resources
- ✅ `401 Unauthorized` for unauthenticated requests
- ✅ `404 Not Found` for non-existent resources
- ✅ JSON responses with proper data structure

Your API should now work perfectly with Postman! 🎉

