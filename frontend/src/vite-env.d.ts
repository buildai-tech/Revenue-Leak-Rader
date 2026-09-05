/// <reference types="vite/client" />

// Extend Vite's ImportMeta env type with our custom VITE_* variables
interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_BACKEND_DEV_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
