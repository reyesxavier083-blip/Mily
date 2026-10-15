/** Fail closed for public deployments while allowing unauthenticated local development. */
export function assertProductionAuthConfig(env = process.env) {
  if (env.NODE_ENV === "production" && !String(env.MILY_API_TOKEN || "").trim()) {
    throw new Error("MILY_API_TOKEN must be configured when NODE_ENV=production.");
  }
}
