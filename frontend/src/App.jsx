import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { FiEye, FiEyeOff } from 'react-icons/fi';
import './App.css';
import './components/popup/modal.css';
import MapKambyan from './components/mapKambyan/MapKambyan';

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === `${name}=`) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function getStoredSession() {
  const storedUser = localStorage.getItem('kambyanUser');
  if (!storedUser) return null;

  try {
    return JSON.parse(storedUser);
  } catch (error) {
    return { name: storedUser, role: '' };
  }
}

function AdminPanel() {
  const [users, setUsers] = useState([]);
  const [images, setImages] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState('');

  const csrfToken = getCookie('csrftoken');

  const refreshAdminData = async (userId = selectedUserId) => {
    setIsLoading(true);
    setMessage('');
    try {
      const [userResponse, imageResponse] = await Promise.all([
        axios.get('/api/admin/users/'),
        axios.get(userId ? `/api/admin/images/?user_id=${encodeURIComponent(userId)}` : '/api/admin/images/'),
      ]);
      setUsers(Array.isArray(userResponse.data) ? userResponse.data : []);
      setImages(Array.isArray(imageResponse.data) ? imageResponse.data : []);
    } catch (error) {
      setMessage(error.response?.data?.error || 'Unable to load admin data.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    refreshAdminData('');
  }, []);

  const handleUserFilterChange = (event) => {
    const nextUserId = event.target.value;
    setSelectedUserId(nextUserId);
    refreshAdminData(nextUserId);
  };

  const toggleClientAccess = async (user) => {
    try {
      const response = await axios.patch(
        `/api/admin/users/${user.id}/`,
        { is_active: !user.is_active },
        {
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
        }
      );
      setUsers((currentUsers) => currentUsers.map((item) => (
        item.id === user.id ? response.data : item
      )));
      setMessage(`${response.data.email} is now ${response.data.is_active ? 'active' : 'disabled'}.`);
    } catch (error) {
      setMessage(error.response?.data?.error || 'Unable to update account access.');
    }
  };

  const deleteClient = async (user) => {
    const confirmed = window.confirm(`Delete ${user.email} and all images permanently?`);
    if (!confirmed) return;

    try {
      await axios.delete(`/api/admin/users/${user.id}/`, {
        headers: { 'X-CSRFToken': csrfToken },
      });
      setUsers((currentUsers) => currentUsers.filter((item) => item.id !== user.id));
      setImages((currentImages) => currentImages.filter((image) => image.owner_id !== user.id));
      setMessage(`${user.email} was deleted.`);
    } catch (error) {
      setMessage(error.response?.data?.error || 'Unable to delete account.');
    }
  };

  const deleteImage = async (image) => {
    const imageName = image.image_name || 'this image';
    const confirmed = window.confirm(`Remove ${imageName} from ${image.owner_email}?`);
    if (!confirmed) return;

    try {
      await axios.delete(`/api/admin/images/${image.id}/`, {
        headers: { 'X-CSRFToken': csrfToken },
      });
      setImages((currentImages) => currentImages.filter((item) => item.id !== image.id));
      setUsers((currentUsers) => currentUsers.map((user) => (
        user.id === image.owner_id
          ? { ...user, image_count: Math.max(0, user.image_count - 1) }
          : user
      )));
      setMessage(`${imageName} was removed.`);
    } catch (error) {
      setMessage(error.response?.data?.error || 'Unable to remove image.');
    }
  };

  return (
    <section className="admin-panel" aria-label="Admin controls">
      <div className="admin-panel-header">
        <div>
          <span className="admin-eyebrow">Verified admin</span>
          <h2>Account access</h2>
        </div>
        <div className="admin-header-actions">
          <button type="button" onClick={() => refreshAdminData()} disabled={isLoading}>
            {isLoading ? 'Loading' : 'Refresh'}
          </button>
        </div>
      </div>

      {message ? <div className="admin-message">{message}</div> : null}

      <div className="admin-grid">
        <div className="admin-section">
          <div className="admin-section-head">
            <h3>Clients</h3>
          </div>
          <div className="admin-list">
            {users.map((user) => (
              <div className="admin-row" key={user.id}>
                <div className="admin-row-main">
                  <strong>{user.name}</strong>
                  <span>{user.email}</span>
                  <small>{user.role} | {user.image_count} images | {user.is_active ? 'active' : 'disabled'}</small>
                </div>
                {user.role === 'admin' || user.is_staff || user.is_superuser ? (
                  <span className="admin-badge">Protected</span>
                ) : (
                  <div className="admin-actions">
                    <button type="button" onClick={() => toggleClientAccess(user)}>
                      {user.is_active ? 'Disable' : 'Enable'}
                    </button>
                    <button type="button" className="danger" onClick={() => deleteClient(user)}>
                      Delete
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="admin-section">
          <div className="admin-section-head">
            <h3>Images</h3>
            <select value={selectedUserId} onChange={handleUserFilterChange}>
              <option value="">All accounts</option>
              {users.filter((user) => user.role !== 'admin').map((user) => (
                <option key={user.id} value={user.id}>{user.email}</option>
              ))}
            </select>
          </div>
          <div className="admin-list admin-image-list">
            {images.map((image) => (
              <div className="admin-row" key={image.id}>
                <div className="admin-row-main">
                  <strong>{image.image_name || 'Uploaded image'}</strong>
                  <span>{image.owner_email}</span>
                  <small>{new Date(image.uploaded_on).toLocaleString()}</small>
                </div>
                {image.image_file ? (
                  <a href={image.image_file} target="_blank" rel="noreferrer">View</a>
                ) : null}
                <button type="button" className="danger" onClick={() => deleteImage(image)}>
                  Remove
                </button>
              </div>
            ))}
            {!images.length ? <div className="admin-empty">No images found.</div> : null}
          </div>
        </div>
      </div>
    </section>
  );
}

function App() {
  const [authMode, setAuthMode] = useState('login');
  const [currentUser, setCurrentUser] = useState(() => getStoredSession()?.name || '');
  const [currentRole, setCurrentRole] = useState(() => getStoredSession()?.role || '');
  const [showAdminPanel, setShowAdminPanel] = useState(false);
  const [isCheckingSession, setIsCheckingSession] = useState(() => Boolean(getStoredSession()));
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [authError, setAuthError] = useState('');
  const [authNotice, setAuthNotice] = useState('');

  const passwordValue = formData.password;
  const normalizePasswordText = (value) => value.toLowerCase().replace(/[^a-z0-9]/g, '');
  const emailLocalPart = formData.email.split('@')[0] || '';
  const nameParts = formData.name.split(/\s+/);
  const similarTerms = [
    formData.name,
    formData.email,
    emailLocalPart,
    ...nameParts,
  ]
    .map(normalizePasswordText)
    .filter((value) => value.length >= 3);
  const normalizedPassword = normalizePasswordText(passwordValue);
  const isTooSimilarToUserInfo = similarTerms.some((term) => (
    normalizedPassword.includes(term) || term.includes(normalizedPassword)
  ));
  const commonPasswords = [
    'password',
    'password123',
    '12345678',
    'qwerty123',
    'admin123',
    'letmein123',
  ];
  const passwordRules = [
    {
      label: 'At least 8 characters',
      isValid: passwordValue.length >= 8,
      showHint: true,
    },
    {
      label: 'Contains uppercase and lowercase letters',
      isValid: /[A-Z]/.test(passwordValue) && /[a-z]/.test(passwordValue),
      showHint: true,
    },
    {
      label: 'Contains a number',
      isValid: /\d/.test(passwordValue),
    },
    {
      label: 'Contains an underscore (_)',
      isValid: passwordValue.includes('_'),
    },
    {
      label: 'No spaces',
      isValid: passwordValue.length > 0 && !/\s/.test(passwordValue),
    },
    {
      label: 'Not too similar to your name or email',
      isValid: normalizedPassword.length > 0 && !isTooSimilarToUserInfo,
      showHint: true,
    },
    {
      label: 'Not a common password',
      isValid: passwordValue.length > 0 && !commonPasswords.includes(normalizedPassword),
    },
    {
      label: 'Not entirely numeric',
      isValid: passwordValue.length > 0 && !/^\d+$/.test(passwordValue),
      showHint: true,
    },
  ];
  const visiblePasswordRules = passwordRules.filter((rule) => rule.showHint);
  const getPasswordRuleError = () => {
    const failedRules = passwordRules.filter((rule) => !rule.isValid).map((rule) => rule.label);
    if (!failedRules.length) return '';
    return `Password does not meet: ${failedRules.join('; ')}.`;
  };
  const isSignupPasswordValid = passwordRules.every((rule) => rule.isValid);

  useEffect(() => {
    const storedSession = getStoredSession();
    if (!storedSession) return;

    axios
      .get('/api/me/')
      .then((response) => {
        const session = {
          name: response.data.name || response.data.email || storedSession.name,
          email: response.data.email || '',
          role: response.data.role || '',
        };
        localStorage.setItem('kambyanUser', JSON.stringify(session));
        setCurrentUser(session.name);
        setCurrentRole(session.role);
      })
      .catch(() => {
        localStorage.removeItem('kambyanUser');
        setCurrentUser('');
        setCurrentRole('');
      })
      .finally(() => setIsCheckingSession(false));
  }, []);

  const handleInputChange = (event) => {
    const { name, value } = event.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    setAuthError('');
    setAuthNotice('');
  };

  const handleAuthSubmit = async (event) => {
    event.preventDefault();
    const email = formData.email.trim();

    if (!email || !formData.password) {
      setAuthError(authMode === 'forgot' ? 'Please enter your email and new password.' : 'Please enter your email and password.');
      return;
    }

    if (authMode === 'signup') {
      if (!formData.name.trim()) {
        setAuthError('Please enter your name.');
        return;
      }

      if (!isSignupPasswordValid) {
        setAuthError(getPasswordRuleError());
        return;
      }

      if (formData.password !== formData.confirmPassword) {
        setAuthError('Passwords do not match.');
        return;
      }
    }

    if (authMode === 'forgot') {
      if (!isSignupPasswordValid) {
        setAuthError(getPasswordRuleError());
        return;
      }

      if (formData.password !== formData.confirmPassword) {
        setAuthError('Passwords do not match.');
        return;
      }

      try {
        const response = await axios.post('/api/forgot-password/', {
          email,
          password: formData.password,
          confirm_password: formData.confirmPassword,
        }, {
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken'),
          },
        });
        setAuthMode('login');
        setFormData({
          name: '',
          email,
          password: '',
          confirmPassword: '',
        });
        setShowPassword(false);
        setAuthNotice(response.data?.message || 'Password reset. Please login with your new password.');
      } catch (error) {
        setAuthError(error.response?.data?.error || 'Unable to reset password.');
      }
      return;
    }

    try {
      const url = authMode === 'signup' ? '/api/signup/' : '/api/login/';
      const payload = authMode === 'signup'
        ? { name: formData.name.trim(), email, password: formData.password }
        : { email, password: formData.password, remember_me: rememberMe };
      const response = await axios.post(url, payload, {
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
      });
      const displayName = response.data.name || response.data.email || email;
      localStorage.setItem('kambyanUser', JSON.stringify({
        name: displayName,
        email: response.data.email || email,
        role: response.data.role || '',
      }));
      setCurrentUser(displayName);
      setCurrentRole(response.data.role || '');
    } catch (error) {
      if (!error.response) {
        setAuthError('Backend server is not running. Start Django on http://localhost:8000 and try again.');
        return;
      }

      if (error.response.status === 404) {
        setAuthError('Authentication API was not found. Restart the React server so the API proxy is loaded.');
        return;
      }

      setAuthError(error.response.data?.error || 'Unable to complete authentication.');
    }
  };

  const switchAuthMode = () => {
    setAuthMode((prev) => (prev === 'login' ? 'signup' : 'login'));
    setShowPassword(false);
    setRememberMe(false);
    setAuthError('');
    setAuthNotice('');
  };

  const openForgotPassword = () => {
    setAuthMode('forgot');
    setShowPassword(false);
    setRememberMe(false);
    setAuthError('');
    setAuthNotice('');
  };

  const handleLogout = async () => {
    try {
      await axios.post('/api/logout/', {}, {
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
      });
    } catch (error) {
      console.error('Logout failed:', error);
    }

    localStorage.removeItem('kambyanUser');
    setCurrentUser('');
    setCurrentRole('');
    setShowAdminPanel(false);
    setFormData({
      name: '',
      email: '',
      password: '',
      confirmPassword: '',
    });
    setShowPassword(false);
    setRememberMe(false);
    setAuthNotice('');
    setAuthMode('login');
  };

  if (isCheckingSession) {
    return (
      <div className="auth-page">
        <div className="auth-panel">
          <div className="auth-brand">
            <span className="auth-eyebrow">Kambyan GUI</span>
            <h1>Checking session</h1>
            <p>Verifying your account access.</p>
          </div>
        </div>
      </div>
    );
  }

  if (!currentUser) {
    return (
      <div className="auth-page">
        <div className="auth-orb auth-orb--1" />
        <div className="auth-orb auth-orb--2" />
        <div className="auth-orb auth-orb--3" />
        <div className="auth-panel">
          <div className="auth-brand">
            <div className="auth-logo" aria-hidden="true">K</div>
            <span className="auth-eyebrow">Kambyan GUI</span>
            <h1>
              {authMode === 'login'
                ? 'Welcome back'
                : authMode === 'forgot'
                  ? 'Reset password'
                  : 'Create account'}
            </h1>
            <p>
              {authMode === 'login'
                ? 'Sign in to continue tree detection and annotation work.'
                : authMode === 'forgot'
                  ? 'Enter your account email and choose a new password.'
                  : 'Set up access to manage uploaded imagery and plotted points.'}
            </p>
          </div>

          <form className="auth-form" onSubmit={handleAuthSubmit}>
            {authMode === 'signup' ? (
              <label>
                Name
                <input
                  type="text"
                  name="name"
                  value={formData.name}
                  onChange={handleInputChange}
                  autoComplete="name"
                  placeholder="Enter your full name"
                />
              </label>
            ) : null}

            <label>
              Email
              <input
                type="email"
                name="email"
                value={formData.email}
                onChange={handleInputChange}
                autoComplete="email"
                placeholder="you@example.com"
              />
            </label>

            <label className="password-field">
              Password
              <input
                type={showPassword ? 'text' : 'password'}
                name="password"
                value={formData.password}
                onChange={handleInputChange}
                autoComplete={authMode === 'login' ? 'current-password' : 'new-password'}
                placeholder="••••••••"
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword((isVisible) => !isVisible)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <FiEyeOff aria-hidden="true" /> : <FiEye aria-hidden="true" />}
              </button>
              {authMode !== 'login' ? (
                <ul className="password-rules" aria-label="Password requirements">
                  {visiblePasswordRules.map((rule) => (
                    <li
                      key={rule.label}
                      className={rule.isValid ? 'password-rule-valid' : 'password-rule-invalid'}
                    >
                      <span className="password-rule-icon" aria-hidden="true">
                        {rule.isValid ? 'OK' : '-'}
                      </span>
                      <span>{rule.label}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </label>

            {authMode === 'login' ? (
              <div className="auth-login-options">
                <label className="remember-me">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(event) => setRememberMe(event.target.checked)}
                  />
                  <span>Remember me for 14 days</span>
                </label>
                <button className="auth-link-button" type="button" onClick={openForgotPassword}>
                  Forgot password?
                </button>
              </div>
            ) : null}

            {authMode !== 'login' ? (
              <label className="password-field">
                Confirm password
                <input
                  type="password"
                  name="confirmPassword"
                  value={formData.confirmPassword}
                  onChange={handleInputChange}
                  autoComplete="new-password"
                  placeholder="••••••••"
                />
              </label>
            ) : null}

            {authNotice ? <div className="auth-notice">{authNotice}</div> : null}
            {authError ? <div className="auth-error">{authError}</div> : null}

            <button className="auth-submit" type="submit">
              {authMode === 'login' ? 'Login' : authMode === 'forgot' ? 'Reset password' : 'Sign up'}
            </button>
          </form>

          <button className="auth-switch" type="button" onClick={switchAuthMode}>
            {authMode === 'login'
              ? 'Need an account? Sign up'
              : 'Already have an account? Login'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`App ${currentRole === 'admin' ? 'App-admin' : ''}`}>
      <MapKambyan
        currentUser={currentUser}
        onLogout={handleLogout}
        isAdmin={currentRole === 'admin'}
        showAdminPanel={showAdminPanel}
        onToggleAdminPanel={() => setShowAdminPanel((isVisible) => !isVisible)}
      >
        {currentRole === 'admin' && showAdminPanel ? (
          <div className="admin-management-page">
            <nav className="admin-return-nav" aria-label="Management navigation">
              <a
                href="#image-display"
                className="admin-return-link"
                aria-label="Return to image display"
                title="Return to image display"
                onClick={(event) => {
                  event.preventDefault();
                  setShowAdminPanel(false);
                }}
              >
                <span aria-hidden="true">←</span>
                <span>Image Display</span>
              </a>
            </nav>
            <AdminPanel />
          </div>
        ) : null}
      </MapKambyan>
    </div>
  );
}




export default App;
