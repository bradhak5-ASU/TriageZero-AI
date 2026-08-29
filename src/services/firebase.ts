/**
 * Firebase Web SDK bootstrap.
 *
 * The values below are Firebase's *public* web configuration: they identify
 * the project to Google's servers and are designed to ship in a browser
 * bundle. They are not a private credential — access is controlled by Firebase
 * Auth rules and by the backend independently verifying every ID token.
 * A backend secret (an ingestion token, a service-account key) must NEVER
 * appear here.
 *
 * Initialization is lazy: with no VITE_FIREBASE_* values configured the app
 * still loads and reports "auth not configured" instead of crashing, which is
 * what keeps local demo mode and the test suite working.
 */
import { type FirebaseApp, initializeApp } from 'firebase/app';
import { type Auth, getAuth } from 'firebase/auth';

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY ?? '',
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN ?? '',
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID ?? '',
  appId: import.meta.env.VITE_FIREBASE_APP_ID ?? '',
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET ?? '',
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID ?? '',
};

/** True when enough public config is present to talk to Firebase. */
export function isFirebaseConfigured(): boolean {
  return Boolean(config.apiKey && config.authDomain && config.projectId);
}

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

/** Returns the Auth instance, or null when Firebase is not configured. */
export function getFirebaseAuth(): Auth | null {
  if (!isFirebaseConfigured()) return null;
  if (!auth) {
    app = app ?? initializeApp(config);
    auth = getAuth(app);
  }
  return auth;
}

/** Test seam: drop the cached instances. */
export function resetFirebaseForTests(): void {
  app = null;
  auth = null;
}
