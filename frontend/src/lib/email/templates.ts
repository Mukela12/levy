const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://levylegal.ai'
const CONTACT_EMAIL = process.env.LEVY_EMAIL_REPLY_TO || 'mukelakatungu@levylegal.ai'
const GITHUB_URL = 'https://github.com/Mukela12'
const GITHUB_LOGO_URL = 'https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png'
const LEVY_LOGO_URL = `${SITE_URL.replace(/\/$/, '')}/levy-logo.svg`

type EmailTemplate = {
  subject: string
  html: string
  text: string
}

type Cta = {
  href: string
  label: string
}

type AnnouncementOptions = {
  preview?: boolean
}

type WelcomeOptions = {
  fullName?: string | null
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function buildHtml({
  eyebrow,
  title,
  intro,
  bodyHtml,
  primaryCta,
  footerNote,
}: {
  eyebrow: string
  title: string
  intro: string
  bodyHtml: string
  primaryCta: Cta
  footerNote: string
}) {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${escapeHtml(title)}</title>
  </head>
  <body style="margin:0;padding:0;background:#f3f1eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#163225;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">${escapeHtml(intro)}</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f1eb;margin:0;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:680px;background:#ffffff;border:1px solid #ddd8cb;border-radius:28px;overflow:hidden;box-shadow:0 20px 50px rgba(17,24,39,0.08);">
            <tr>
              <td style="height:6px;background:linear-gradient(90deg,#0a7a3d 0%,#12633a 70%,#d87924 100%);font-size:0;line-height:0;">&nbsp;</td>
            </tr>
            <tr>
              <td style="background:linear-gradient(180deg,#23262b 0%,#2d3137 100%);padding:36px 40px 28px;color:#ffffff;border-bottom:1px solid #3b4048;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  <tr>
                    <td style="vertical-align:top;">
                      <table role="presentation" cellspacing="0" cellpadding="0">
                        <tr>
                          <td style="width:78px;height:78px;border-radius:22px;background:#1b1e23;border:1px solid #3b4048;text-align:center;vertical-align:middle;box-shadow:0 8px 24px rgba(0,0,0,0.24);">
                            <img src="${LEVY_LOGO_URL}" width="50" height="50" alt="Levy logo" style="display:block;width:50px;height:50px;margin:14px auto;" />
                          </td>
                        </tr>
                      </table>
                      <div style="font-size:12px;letter-spacing:0.16em;text-transform:uppercase;color:#a7e0ba;font-weight:700;margin-top:18px;">${escapeHtml(eyebrow)}</div>
                      <h1 style="margin:12px 0 10px;font-size:34px;line-height:1.12;font-weight:800;color:#4cc26f;">${escapeHtml(title)}</h1>
                      <p style="margin:0;font-size:16px;line-height:1.75;color:#d2d7d4;max-width:540px;">${escapeHtml(intro)}</p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>

            <tr>
              <td style="padding:34px 40px 20px;">
                ${bodyHtml}
              </td>
            </tr>

            <tr>
              <td style="padding:6px 40px 10px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  <tr>
                    <td style="padding-bottom:12px;">
                      <a href="${primaryCta.href}" style="display:block;background:#0a7a3d;color:#ffffff;text-decoration:none;font-size:15px;font-weight:700;padding:15px 22px;border-radius:16px;text-align:center;">${escapeHtml(primaryCta.label)}</a>
                    </td>
                  </tr>
                  <tr>
                    <td>
                      <a href="${GITHUB_URL}" style="display:block;background:#ffffff;color:#111827;text-decoration:none;font-size:15px;font-weight:700;padding:14px 18px;border-radius:16px;border:1px solid #dcdcdc;">
                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                          <tr>
                            <td style="width:28px;vertical-align:middle;">
                              <img src="${GITHUB_LOGO_URL}" width="20" height="20" alt="GitHub" style="display:block;width:20px;height:20px;border:0;" />
                            </td>
                            <td style="vertical-align:middle;color:#111827;">View Mukela12 on GitHub</td>
                          </tr>
                        </table>
                      </a>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>

            <tr>
              <td style="padding:28px 40px 40px;">
                <div style="height:1px;background:#e7e1d6;margin-bottom:24px;"></div>
                <p style="margin:0 0 8px;font-size:15px;line-height:1.8;color:#244233;">Thanks again for being part of Levy.</p>
                <p style="margin:0;font-size:15px;line-height:1.8;color:#244233;">Mukela Katungu<br /><span style="color:#6b7c73;">Founder, Levy</span></p>
              </td>
            </tr>
          </table>

          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:680px;">
            <tr>
              <td style="padding:18px 20px 0;text-align:center;font-size:12px;line-height:1.7;color:#708476;">
                ${footerNote}<br />
                Contact: <a href="mailto:${CONTACT_EMAIL}" style="color:#0a7a3d;text-decoration:none;">${CONTACT_EMAIL}</a>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>`
}

export function renderWelcomeEmail({ fullName }: WelcomeOptions = {}): EmailTemplate {
  const greeting = fullName?.trim() ? `Hi ${escapeHtml(fullName.trim())},` : 'Hi,'
  const bodyHtml = `
    <p style="margin:0 0 18px;font-size:16px;line-height:1.8;color:#244233;">${greeting}</p>
    <p style="margin:0 0 18px;font-size:16px;line-height:1.8;color:#244233;">Welcome to Levy. You now have access to a legal research and drafting workspace built around Zambian legal workflows.</p>
    <p style="margin:0 0 24px;font-size:16px;line-height:1.8;color:#244233;">Levy is still evolving quickly, so expect regular improvements in legal coverage, reliability, document tooling, and interface quality as we move from test mode into a stronger production product.</p>

    <div style="background:#f7faf7;border:1px solid #dbe8dd;border-radius:20px;padding:22px 22px 6px;">
      <div style="font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#0d6b37;margin-bottom:14px;">What you can use Levy for</div>
      <div style="font-size:15px;line-height:1.8;color:#224132;">
        <p style="margin:0 0 12px;"><strong>Ask legal questions:</strong> get answers grounded in Zambian legal materials.</p>
        <p style="margin:0 0 12px;"><strong>Work with source documents:</strong> upload, inspect, and use legal materials directly in chat.</p>
        <p style="margin:0 0 12px;"><strong>Draft faster:</strong> use Levy as a legal productivity assistant for research and drafting support.</p>
      </div>
    </div>

    <div style="background:#fffaf4;border:1px solid #f1dcc2;border-radius:20px;padding:22px;margin-top:14px;">
      <div style="font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#b7651d;margin-bottom:12px;">Stay in touch</div>
      <p style="margin:0 0 14px;font-size:15px;line-height:1.8;color:#4b3622;">If you have feedback, questions, or issues, contact me directly at <a href="mailto:${CONTACT_EMAIL}" style="color:#b7651d;text-decoration:none;font-weight:700;">${CONTACT_EMAIL}</a>.</p>
      <p style="margin:0;font-size:15px;line-height:1.8;color:#4b3622;">I’m also sharing my GitHub below if you’d like to see more of my work.</p>
    </div>
  `

  return {
    subject: 'Welcome to Levy',
    html: buildHtml({
      eyebrow: 'Levy Legal AI',
      title: 'Welcome to Levy',
      intro: 'Thank you for joining Levy. You’re now part of the early group shaping a legal AI product built for Zambia.',
      bodyHtml,
      primaryCta: { href: SITE_URL, label: 'Open Levy' },
      footerNote: 'You’re receiving this because you created a Levy account.',
    }),
    text:
      `Welcome to Levy.\n\n` +
      `You now have access to a legal research and drafting workspace built around Zambian legal workflows.\n\n` +
      `If you have feedback, questions, or issues, contact me directly at ${CONTACT_EMAIL}.\n` +
      `GitHub: ${GITHUB_URL}\n` +
      `Site: ${SITE_URL}`,
  }
}

export function renderTesterAnnouncementEmail({ preview = false }: AnnouncementOptions = {}): EmailTemplate {
  const subject = preview
    ? 'Preview | Levy just got better'
    : 'Levy just got better: more reliable chats, better answers, and a new home'

  const bodyHtml = `
    <p style="margin:0 0 18px;font-size:16px;line-height:1.8;color:#244233;">Hi,</p>
    <p style="margin:0 0 18px;font-size:16px;line-height:1.8;color:#244233;">If you’ve used Levy so far, you’ve been part of the early group helping test it. This is my first proper update to you, and I wanted to say thank you for using it while it’s still growing.</p>
    <p style="margin:0 0 24px;font-size:16px;line-height:1.8;color:#244233;">This week’s work was all about making Levy more dependable, easier to use, and more useful for real legal work and legal study.</p>

    <div style="background:#f7faf7;border:1px solid #dbe8dd;border-radius:20px;padding:22px 22px 6px;">
      <div style="font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#0d6b37;margin-bottom:14px;">What’s new for you</div>
      <div style="font-size:15px;line-height:1.8;color:#224132;">
        <p style="margin:0 0 12px;"><strong>Your chats are less likely to disappear:</strong> Levy now does a better job of finishing and saving answers even when your connection is unstable or you leave the app while it is still thinking.</p>
        <p style="margin:0 0 12px;"><strong>Fewer technical failures:</strong> I fixed a major model issue that had caused no-reply failures, and Levy now handles provider problems more gracefully instead of showing raw technical errors.</p>
        <p style="margin:0 0 12px;"><strong>Better legal coverage:</strong> I expanded and cleaned up parts of the legal library so Levy can find more useful material, including improvements to intellectual property law coverage and broader Act visibility.</p>
        <p style="margin:0 0 12px;"><strong>Better support for authorities and case law:</strong> Levy can now surface relevant court judgments in a clearer way, so it is easier to spot useful precedent when a question needs authority.</p>
        <p style="margin:0 0 12px;"><strong>Smoother mobile experience:</strong> I fixed interface issues that made parts of Levy feel jumpy or awkward on phones, since most of you are using it on mobile.</p>
        <p style="margin:0 0 12px;"><strong>New official home:</strong> Levy is now moving under <a href="${SITE_URL}" style="color:#0a7a3d;text-decoration:none;font-weight:700;">levylegal.ai</a>.</p>
      </div>
    </div>

    <div style="background:#fffaf4;border:1px solid #f1dcc2;border-radius:20px;padding:22px;margin-top:14px;">
      <div style="font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#b7651d;margin-bottom:12px;">Stay in touch</div>
      <p style="margin:0 0 14px;font-size:15px;line-height:1.8;color:#4b3622;">If Levy gives you a bad answer, loses context, misses a source you expected, or you simply have an idea for how it should improve, contact me directly at <a href="mailto:${CONTACT_EMAIL}" style="color:#b7651d;text-decoration:none;font-weight:700;">${CONTACT_EMAIL}</a>.</p>
      <p style="margin:0;font-size:15px;line-height:1.8;color:#4b3622;">Your feedback is directly shaping what gets built next.</p>
    </div>
  `

  return {
    subject,
    html: buildHtml({
      eyebrow: preview ? 'Levy Preview Send' : 'Levy Legal AI',
      title: 'Levy Just Got Better',
      intro:
        'Thank you for testing Levy in its early phase. Here is a simple update on what changed this week and what it means for you.',
      bodyHtml,
      primaryCta: { href: SITE_URL, label: 'Open Levy at levylegal.ai' },
      footerNote: preview
        ? 'Preview email sent from Levy’s announcement template.'
        : 'You’re receiving this because you interacted with Levy during its early test phase.',
    }),
    text:
      `Levy just got better.\n\n` +
      `This week I made Levy more reliable, fixed major no-reply failures, improved legal coverage, improved case-law support, made the mobile experience smoother, and moved Levy under ${SITE_URL}.\n\n` +
      `If Levy gives you a bad answer, loses context, or misses something you expected, contact me at ${CONTACT_EMAIL}.\n` +
      `GitHub: ${GITHUB_URL}`,
  }
}
