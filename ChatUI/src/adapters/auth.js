// Authentication adapter interface
export class AuthAdapter {
  async getCurrentUser() {
    throw new Error('getCurrentUser must be implemented');
  }

  async login(credentials) {
    throw new Error('login must be implemented');
  }

  async logout() {
    throw new Error('logout must be implemented');
  }

  async refreshToken() {
    throw new Error('refreshToken must be implemented');
  }

  onAuthStateChange(callback) {
    throw new Error('onAuthStateChange must be implemented');
  }
}

// Mock Authentication Adapter (for standalone mode)
export class MockAuthAdapter extends AuthAdapter {
  constructor() {
    super();
    this.currentUser = {
      id: '56132',
      username: 'John Doe',
      email: 'john.doe@example.com',
      avatar: '/default-avatar.png',
      role: 'user'
    };
    this.authStateCallbacks = [];
  }

  async getCurrentUser() {
    return this.currentUser;
  }

  async login(credentials) {
    // Mock login
    console.log('Mock login with:', credentials);
    this.notifyAuthStateChange(this.currentUser);
    return { success: true, user: this.currentUser };
  }

  async logout() {
    this.currentUser = null;
    this.notifyAuthStateChange(null);
    return { success: true };
  }

  async refreshToken() {
    return { success: true, token: 'mock-token' };
  }

  onAuthStateChange(callback) {
    this.authStateCallbacks.push(callback);
    // Immediately call with current state
    callback(this.currentUser);
  }

  notifyAuthStateChange(user) {
    this.authStateCallbacks.forEach(callback => callback(user));
  }

  setUser(user) {
    this.currentUser = user;
    this.notifyAuthStateChange(user);
  }
}

// External Authentication Adapter (for embedded mode)
export class ExternalAuthAdapter extends AuthAdapter {
  constructor(externalAuthProvider) {
    super();
    this.externalAuth = externalAuthProvider;
  }

  async getCurrentUser() {
    return this.externalAuth.getCurrentUser();
  }

  async login(credentials) {
    return this.externalAuth.login(credentials);
  }

  async logout() {
    return this.externalAuth.logout();
  }

  async refreshToken() {
    return this.externalAuth.refreshToken();
  }

  onAuthStateChange(callback) {
    return this.externalAuth.onAuthStateChange(callback);
  }
}

// Token-based Authentication Adapter
export class TokenAuthAdapter extends AuthAdapter {
  constructor(apiBaseUrl, tokenKey = 'chatui_token') {
    super();
    this.apiBaseUrl = apiBaseUrl;
    this.tokenKey = tokenKey;
    this.currentUser = null;
    this.authStateCallbacks = [];
  }

  async getCurrentUser() {
    if (this.currentUser) return this.currentUser;

    const token = localStorage.getItem(this.tokenKey);
    if (!token) return null;

    try {
      const response = await fetch(`${this.apiBaseUrl}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.ok) {
        this.currentUser = await response.json();
        return this.currentUser;
      }
    } catch (error) {
      console.error('Auth error:', error);
    }

    return null;
  }

  async login(credentials) {
    try {
      const response = await fetch(`${this.apiBaseUrl}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials)
      });

      if (response.ok) {
        const data = await response.json();
        localStorage.setItem(this.tokenKey, data.token);
        this.currentUser = data.user;
        this.notifyAuthStateChange(this.currentUser);
        return { success: true, user: this.currentUser };
      }
    } catch (error) {
      console.error('Login error:', error);
    }

    return { success: false, error: 'Login failed' };
  }

  async logout() {
    localStorage.removeItem(this.tokenKey);
    this.currentUser = null;
    this.notifyAuthStateChange(null);
    return { success: true };
  }

  async refreshToken() {
    // Implementation depends on your refresh token strategy
    return { success: true };
  }

  onAuthStateChange(callback) {
    this.authStateCallbacks.push(callback);
    // Immediately call with current state
    callback(this.currentUser);
  }

  notifyAuthStateChange(user) {
    this.authStateCallbacks.forEach(callback => callback(user));
  }
}
