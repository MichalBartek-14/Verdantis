// Gates each pilot client's dashboard behind its OWN HTTP Basic Auth
// username/password, while leaving the public briefing pages (/, intro-2/
// 3.html, sk/, plots.html) open to anyone. This pilot has no accounts
// system or database - just "don't let a stranger with the URL browse a
// client's data" via one shared secret per client. Runs on Netlify Edge
// Functions (Deno), which are available on every plan including free/
// Starter and have an invocation quota far beyond what two low-traffic
// pilot clients will ever hit - check Site > Usage & Billing if that ever
// becomes a concern, but it won't for a pilot.
//
// Credentials live ONLY in this site's Netlify environment variables
// (Site configuration -> Environment variables) - never commit them here.
// Adding a third client: add a row below + the matching two env vars in
// Netlify, then redeploy (env var changes need a new deploy to take
// effect - trigger one from the Deploys tab if you don't push a commit).
const PROTECTED = [
  { prefix: "/c/valice/", userEnv: "VALICE_USER", passEnv: "VALICE_PASS", realm: "Verdantis - Valice" },
  { prefix: "/c/vepor/", userEnv: "VEPOR_USER", passEnv: "VEPOR_PASS", realm: "Verdantis - Vepor" },
];

export default async (request, context) => {
  const path = new URL(request.url).pathname;
  const rule = PROTECTED.find((p) => path.startsWith(p.prefix));
  if (!rule) return context.next(); // public page - no auth required

  const user = Deno.env.get(rule.userEnv);
  const pass = Deno.env.get(rule.passEnv);

  if (!user || !pass) {
    // Env vars not set yet for this client - fail CLOSED (block access)
    // rather than silently letting everyone through because someone
    // forgot a step. See README's "Client access control" section.
    return new Response(
      "This client dashboard isn't configured yet - missing " + rule.userEnv + "/" + rule.passEnv + ".",
      { status: 503 }
    );
  }

  const expected = "Basic " + btoa(`${user}:${pass}`);
  const given = request.headers.get("authorization");

  if (given !== expected) {
    return new Response("Authentication required.", {
      status: 401,
      headers: { "WWW-Authenticate": `Basic realm="${rule.realm}"` },
    });
  }

  return context.next();
};

export const config = { path: "/c/*" };
