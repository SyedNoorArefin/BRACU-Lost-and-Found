from app import app, db

with app.app_context():
    # Create all tables
    db.create_all()
    print("Database tables created successfully!")
    print("Tables created:")
    print("- User")
    print("- LostItem") 
    print("- Notification")
    print("- ActivityLog")
    print("- Conversation")
    print("- Message")
    print("- EmailVerification")
    print("- Report")
    print("- UserSuspension")
    print("- UserPoints")
    print("- UserBadge")
    print("- ItemReturn")
