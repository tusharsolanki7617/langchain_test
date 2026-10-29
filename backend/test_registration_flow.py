#!/usr/bin/env python3
"""
Test script to create a new account and login after approval
"""
import requests
from time import sleep

BASE_URL = "http://127.0.0.1:5002"

def create_account():
    """Register a new student account"""
    print("=" * 60)
    print("STEP 1: Creating new student account...")
    print("=" * 60)
    
    signup_data = {
        'first_name': 'John',
        'last_name': 'Doe',
        'email': 'johndoe@example.com',
        'password': 'password123',
        'confirm_password': 'password123',
        'role': 'student',
        'institute': 'MIT',
        'roll_number': 'CS2024999',
        'class_year': '3rd Year · B.Tech CS'
    }
    
    session = requests.Session()
    response = session.post(f"{BASE_URL}/signup", data=signup_data, allow_redirects=False)
    
    if response.status_code in [200, 302]:
        print("✓ Account created successfully!")
        print(f"  Email: {signup_data['email']}")
        print(f"  Password: {signup_data['password']}")
        print(f"  Role: {signup_data['role']}")
        print(f"  Institute: {signup_data['institute']}")
        print("\n⏳ Account is pending admin approval...")
        return signup_data['email'], signup_data['password'], session
    else:
        print(f"✗ Failed to create account. Status: {response.status_code}")
        return None, None, None


def approve_account(email):
    """Admin approves the account"""
    print("\n" + "=" * 60)
    print("STEP 2: Admin approving the account...")
    print("=" * 60)
    
    # Login as admin first
    admin_session = requests.Session()
    login_data = {
        'email': 'admin@edux.com',
        'password': 'admin123',
        'role': 'admin'
    }
    
    response = admin_session.post(f"{BASE_URL}/login", data=login_data)
    
    if response.status_code != 200:
        print("✗ Failed to login as admin")
        return False
    
    print("✓ Logged in as admin")
    
    # Get user ID from database check (we'll use the API)
    # First, get the pending users from the dashboard
    response = admin_session.get(f"{BASE_URL}/dashboard/admin")
    
    if "johndoe@example.com" in response.text:
        print(f"✓ Found pending user: {email}")
        
        # Try to find user ID and approve (simulating through SQL for demo)
        # In real scenario, you'd parse the HTML or use proper API
        # For this demo, let's use direct database query
        import sys
        sys.path.insert(0, '/Users/tushar/Desktop/langchain_test/milestone-2')
        from database import db
        
        user = db.find_user_by_email(email)
        if user:
            user_id = user['id']
            approve_response = admin_session.post(f"{BASE_URL}/api/admin/approve/{user_id}")
            
            if approve_response.status_code == 200:
                print(f"✓ Account approved! User ID: {user_id}")
                return True
            else:
                print(f"✗ Failed to approve account. Status: {approve_response.status_code}")
                return False
    
    print("✗ User not found in pending list")
    return False


def login_as_user(email, password):
    """Login with the newly created account"""
    print("\n" + "=" * 60)
    print("STEP 3: Logging in with new account...")
    print("=" * 60)
    
    session = requests.Session()
    login_data = {
        'email': email,
        'password': password,
        'role': 'student'
    }
    
    response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=True)
    
    if response.status_code == 200 and "dashboard" in response.url.lower():
        print("✓ Login successful!")
        print(f"  Redirected to: {response.url}")
        
        # Check if we can access the dashboard
        if "Welcome" in response.text or "dashboard" in response.text.lower():
            print("✓ Successfully accessed student dashboard")
            return True
        else:
            print("⚠ Logged in but dashboard content unclear")
            return True
    else:
        print(f"✗ Login failed. Status: {response.status_code}")
        print(f"  URL: {response.url}")
        return False


def main():
    print("\n" + "🧪 TESTING COMPLETE REGISTRATION AND LOGIN FLOW " + "\n")
    
    # Step 1: Create account
    email, password, session = create_account()
    if not email:
        print("\n❌ Test failed at account creation")
        return
    
    sleep(1)
    
    # Step 2: Approve account (as admin)
    if not approve_account(email):
        print("\n❌ Test failed at account approval")
        return
    
    sleep(1)
    
    # Step 3: Login with new account
    if login_as_user(email, password):
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print(f"\nYou can now login at: {BASE_URL}/login")
        print(f"Email: {email}")
        print(f"Password: {password}")
    else:
        print("\n❌ Test failed at login")


if __name__ == "__main__":
    main()
