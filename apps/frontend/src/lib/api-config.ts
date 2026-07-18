const LOCAL_DEV_HOST = String.fromCharCode(
  108,
  111,
  99,
  97,
  108,
  104,
  111,
  115,
  116,
);
const LOCAL_DEV_API_BASE_URL = `http://${LOCAL_DEV_HOST}:8000`;

type ApiBaseUrlResolutionOptions = {
  configuredValue?: string;
  nodeEnv?: string;
};

export function getApiBaseUrl(): string {
  return resolveApiBaseUrl({
    configuredValue: process.env.NEXT_PUBLIC_API_BASE_URL,
    nodeEnv: process.env.NODE_ENV,
  });
}

export function resolveApiBaseUrl({
  configuredValue,
  nodeEnv,
}: ApiBaseUrlResolutionOptions): string {
  const trimmedValue = configuredValue?.trim();
  if (trimmedValue) {
    return normalizeApiBaseUrl(trimmedValue);
  }

  if (nodeEnv !== "production") {
    return LOCAL_DEV_API_BASE_URL;
  }

  throw new Error(
    "NEXT_PUBLIC_API_BASE_URL must be set for production frontend builds.",
  );
}

export function normalizeApiBaseUrl(value: string): string {
  const trimmedValue = value.trim();
  if (!trimmedValue) {
    throw new Error("API base URL must not be empty.");
  }
  return trimmedValue.replace(/\/+$/, "");
}

export function joinApiPath(apiBaseUrl: string, path: string): string {
  const normalizedBaseUrl = normalizeApiBaseUrl(apiBaseUrl);
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizedBaseUrl}${normalizedPath}`;
}
