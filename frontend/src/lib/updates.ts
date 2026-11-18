/**
 * Levy's monthly updates: what changed, and how to use it.
 *
 * One entry a month, newest first. Each is an article at /updates/<slug>, and
 * the update email is only a short list that links here (the pattern is
 * Railway's weekly changelog: the email names what shipped, the page explains
 * it).
 *
 * How to write one, so it stays easy to read:
 *  - Talk to the reader as "you". Short sentences, one idea each.
 *  - A section opens with what Levy now does, not with history.
 *  - Say how to use it: where to tap, what to tell Levy, a question to try.
 *  - Say the limit plainly in `note` when there is one.
 *  - Only what is live on the day of writing, with figures measured that day.
 *
 * Paragraphs may use **bold** and [links](/path). A section's `id` is its
 * anchor on the page; the update email links to these, so do not rename one
 * after its email has gone out.
 */

export type UpdateImage = {
  src: string
  alt: string
  width: number
  height: number
  caption: string
}

export type UpdateSection = {
  id: string
  title: string
  image?: UpdateImage
  body: string[]
  /** How to use it: one step, or a short numbered list. */
  how?: string[]
  /** A question that opens in Levy's message box, ready to send. */
  tryIt?: string
  /** A limit worth knowing before relying on it. */
  note?: string
}

export type Update = {
  slug: string
  /** "November 2026" */
  month: string
  /** The day it was published, as YYYY-MM-DD. */
  date: string
  title: string
  /** One sentence, for the list of updates and for search results. */
  summary: string
  intro: string
  sections: UpdateSection[]
  smaller?: string[]
}

export const updates: Update[] = [
  {
    slug: 'november-2026',
    month: 'November 2026',
    date: '2026-11-18',
    title: 'Documents set like court papers, cases checked against ZambiaLII, and final pay',
    summary:
      'Drafts now look like the documents a Zambian court would recognise, cases are checked against ZambiaLII, and Levy works out final pay.',
    intro:
      'Drafts from Levy now look like the documents a Zambian court or law firm would produce. This month Levy also started checking cases against ZambiaLII, learned to work out final pay, and added 500 judgments to its library.',
    sections: [
      {
        id: 'court-documents',
        title: 'Documents set like Zambian court papers',
        image: {
          src: '/updates/november-2026/court-paper.webp',
          alt: 'The top of a statement of claim drafted by Levy: the High Court named at the top left, the cause number at the top right, the parties in bold capitals with their titles at the right margin, and the title between two rules.',
          width: 1060,
          height: 900,
          caption: 'A statement of claim as Levy now sets it. The names are made up.',
        },
        body: [
          'Ask Levy for an affidavit, a summons or a statement of claim, and the page now looks the way the courts set their own documents. The court is named at the top left with the cause number opposite. The parties are in bold capitals with their titles at the right margin, and the name of the document sits between two rules.',
          'The layout comes from the courts’ own judgments and the forms in their rules. Court papers use a Bookman typeface, numbered paragraphs and a 4 cm left margin for binding. An affidavit ends with a proper jurat, and each exhibit gets its own sheet to mark it.',
          'Agreements and letters changed too. Clause numbers stand in their own column, signature blocks have ruled lines to sign on, and each schedule starts on a new page. The Word download follows the same layout, so you can keep editing.',
        ],
        how: [
          'Tell Levy the court, the parties, and the cause number if you have one. If the case was started by writ, say so, and the heading keeps Plaintiff and Defendant.',
        ],
        tryIt: 'Draft an affidavit in support of an application for an interim injunction in the High Court at Lusaka.',
        note: 'A registry or a judge may ask for something different, and Levy can still get a fact or the law wrong. Read every draft, and have a lawyer look at anything you will file or sign.',
      },
      {
        id: 'missing-details',
        title: 'Drafts that tell you what is missing',
        image: {
          src: '/updates/november-2026/blanks.webp',
          alt: 'The first page of a tenancy agreement drafted by Levy, with the details it still needs highlighted in yellow: the date, the company registration number, the registered address and the tenant’s NRC number.',
          width: 1060,
          height: 780,
          caption: 'What Levy still needs is highlighted on the page and listed under the draft.',
        },
        body: [
          'A draft used to come back with gaps and no clear way to close them. Now every draft lists what is still missing, in plain words, right under the document. The same gaps are highlighted on the page.',
          'Reply with the details and Levy puts each one in its place and hands back the finished document. It does not rewrite the rest.',
        ],
        how: [
          'Send everything in one message. For example: “The landlord’s company number is 120190012345, the tenant’s NRC is 234567/10/1, and it will be signed on 20 November.”',
        ],
      },
      {
        id: 'letterhead',
        title: 'Your letterhead on your letters',
        body: [
          'Upload your logo once, and Levy prints it as the letterhead on the letters it drafts for you, in the PDF and in the Word file.',
        ],
        how: [
          'Open **Templates** and upload your logo as a PNG or JPG.',
          'Add your organisation’s name, address, phone and email, one to a line.',
          'Ask Levy for a letter. It uses the letterhead without being told.',
        ],
      },
      {
        id: 'citations',
        title: 'Citations traced to what Levy read',
        body: [
          'A citation only helps you if Levy actually read the case. Levy now traces every case and Act it cites back to the text it opened while writing your answer.',
          'If a citation does not trace, Levy goes back and corrects it. Anything it still could not check is marked under the answer, so you know to open the source yourself.',
        ],
      },
      {
        id: 'zambialii',
        title: 'Cases checked against ZambiaLII',
        body: [
          'Levy’s library holds 1,665 judgments, but not every Zambian case. When an answer cites a case the library does not hold, Levy now looks it up in ZambiaLII’s index, through Laws.Africa, the service behind ZambiaLII.',
          'If the case is listed, you see **Listed on ZambiaLII** under the answer, with a link to open it there. If it is not, Levy tells you it could not find it.',
        ],
        tryIt: 'Find Zambian authority on reinstatement as a remedy for unfair dismissal.',
        note: 'This is a trial. The index gives Levy a summary of the judgment, not its full text, so open the judgment itself before you rely on it.',
      },
      {
        id: 'final-pay',
        title: 'Final pay and gratuity',
        body: [
          'Ask what someone is owed when a job ends, and Levy now works it out line by line: wages to the last day, leave days, gratuity, notice pay, and the tax on each.',
          'It works from either side. An employee can check a final payslip, and an employer can work out what a package must contain. Domestic workers are covered too, with the 2023 minimum wage and separation benefits.',
        ],
        how: ['Give Levy the start date, the last day, the monthly pay and how the job ended.'],
        tryIt: 'I earned K8,000 a month from 1 March 2022 to 31 October 2026 on a fixed-term contract. What is my final pay?',
        note: 'Check the result against your contract. It may give you more than the legal minimum.',
      },
      {
        id: 'photos',
        title: 'Photograph a document',
        body: [
          'Most of you use Levy on a phone, and most documents arrive on paper. You can now attach a photo of a letter, a payslip or a court paper, and Levy reads it along with your question.',
        ],
        how: ['Tap the attach button beside the message box, choose the photo, then ask your question.'],
      },
      {
        id: 'library',
        title: '500 more judgments, and the Gazette',
        body: [
          'The case law library has grown from 1,165 judgments to 1,665.',
          'Levy can also search the Government Gazette, where statutory instruments and commencement notices are published. That helps when you need to know whether a law has actually come into force.',
          'There are three new step-by-step guides: getting a protection order, starting a divorce, and where to get help after gender-based violence.',
        ],
        tryIt: 'How do I get a protection order in Zambia, step by step?',
      },
    ],
    smaller: [
      'On a phone, the menu bar hides while you read an answer and returns when you scroll up.',
      'Recent chats are ordered by when you last used them.',
      'Levy knows today’s date, so a letter is dated correctly and a deadline is counted from the right day.',
      'You can delete your account and everything in it from your profile page.',
    ],
  },
  {
    slug: 'october-2026',
    month: 'October 2026',
    date: '2026-10-08',
    title: 'Payslip checks, warnings about outdated law, and stronger source checks',
    summary:
      'A pay calculator that checks a payslip, flags on repealed law, and quotations checked against the text.',
    intro:
      'This month’s work came from what you raised while using Levy for research, drafting and pay questions.',
    sections: [
      {
        id: 'payslips',
        title: 'Check a payslip',
        body: [
          'Levy now has a pay calculator. Give it a salary and it works out overtime and the statutory deductions.',
          'Paste in the figures from a payslip and Levy compares them with the rules, then flags anything missing or underpaid.',
        ],
        tryIt: 'My basic pay is K6,500 a month and I worked 12 hours of overtime. What should my payslip show?',
      },
      {
        id: 'outdated-law',
        title: 'Warnings about outdated law',
        body: [
          'Sources and citations now flag a provision that has been repealed, and a law whose commencement Levy could not confirm. If an answer leans on an old text, you can see it.',
        ],
      },
      {
        id: 'quotations',
        title: 'Quotations checked against the text',
        body: [
          'When Levy quotes a judgment or an Act, it checks the quotation against the text in its library. Where it has the information, it also shows how later judgments have treated a case.',
        ],
        note: 'Where there is not enough evidence, the result stays marked as unverified. These checks help you inspect an answer. They do not prove that every legal conclusion is right.',
      },
      {
        id: 'phone-downloads',
        title: 'Easier downloads on a phone',
        body: [
          'Download links and sharing work better on phones. An answer that was cut short can pick up where it stopped, and Levy tells you when it could not read an attachment.',
        ],
      },
      {
        id: 'legislation',
        title: '22 more Acts',
        body: [
          'The library gained 22 Acts and amendments from Parliament. The text of 105 documents already in it was cleaned up, including key employment and company law.',
        ],
      },
    ],
  },
  {
    slug: 'september-2026',
    month: 'September 2026',
    date: '2026-09-11',
    title: 'Every citation checked, and more than 1,100 judgments',
    summary:
      'Levy marks which of its citations it has verified, the case law library passes 1,100 judgments, and every source opens.',
    intro:
      'Lawyers keep asking a fair question: how do I know Levy is not making up the cases it cites? Most of this month’s work is an answer to that.',
    sections: [
      {
        id: 'checked-citations',
        title: 'Every citation is checked',
        body: [
          'Under each answer, Levy lists the cases and Acts it cited and checks each one against its library. The ones it finds are marked verified and open with a tap. The rest are marked as not in the library, so you know to check them yourself.',
        ],
        note: 'Verified means the case or Act is real and in the library. It does not mean Levy described it correctly, so open the source before you rely on it.',
      },
      {
        id: 'judgments',
        title: 'More than 1,100 judgments',
        body: [
          'The case law library grew from 146 judgments to 1,137, from the Supreme Court, the Court of Appeal, the Constitutional Court and the High Court.',
          'All of them come from the Judiciary’s own published archive. Each is labelled by court from the judgment’s own text, so a High Court decision is never passed off as a Supreme Court one.',
        ],
      },
      {
        id: 'court-fees',
        title: 'Court fees and rules',
        body: [
          'The Judiciary’s fee schedules and several sets of court rules are now in the library. Ask what it costs to file something, and the answer comes from the schedule itself.',
        ],
        tryIt: 'What is the filing fee for a writ of summons in the High Court?',
      },
      {
        id: 'sources-open',
        title: 'Every source opens',
        body: [
          'Tap a cited source and you get the document. Where Levy does not hold the PDF, it shows the full text and links to the original on the official site.',
        ],
      },
      {
        id: 'ziale',
        title: 'Revising for ZIALE',
        body: [
          'Several of you use Levy to prepare for ZIALE, and it works well for that. Paste in a problem question or a Trial Advocacy scenario and ask Levy to critique your answer. Or ask for revision notes on a procedure, with the rules and cases behind each step.',
        ],
      },
    ],
    smaller: [
      'A bug that stopped some drafted documents from downloading is fixed.',
      'If your connection drops while Levy is answering, it picks up the finished answer once it is saved.',
      'Levy starts with the answer, not with a description of what it is about to search.',
    ],
  },
  {
    slug: 'august-2026',
    month: 'August 2026',
    date: '2026-08-10',
    title: 'Case files, drafts on the first ask, and terminal benefits from real dates',
    summary:
      'Levy keeps a whole case in one place, writes the document when you ask for it, and calculates terminal benefits from the contract’s dates.',
    intro:
      'This month went into the things people kept needing and not finding while working on real matters.',
    sections: [
      {
        id: 'case-files',
        title: 'Case files',
        body: [
          'If you are running a real case, Levy can hold it in one place: the parties, the court, the cause number, key dates and every draft.',
          'It remembers across sessions, so you do not explain your situation again each time you come back. Levy offers to open a case file when it sees you are working on a real matter.',
        ],
      },
      {
        id: 'first-ask',
        title: 'Ask for a document, get a document',
        body: [
          'Levy now writes the draft on the first ask. Anything it does not know is marked with a clear placeholder, where before it interviewed you first.',
          'Every draft also comes back as clean text, so you can copy it straight into Word as well as download the file.',
        ],
      },
      {
        id: 'terminal-benefits',
        title: 'Terminal benefits from real dates',
        body: [
          'The entitlements calculator takes the actual dates from a contract and works out the service period itself. It works from either side: what you are owed, or what a package must contain.',
        ],
      },
      {
        id: 'kwacha',
        title: 'Fines and fees in kwacha',
        body: [
          'Zambian law writes penalties in penalty units and government charges in fee units. Levy now converts them, so you get a figure in kwacha that you can act on.',
        ],
        tryIt: 'How much is a fine of 3,000 penalty units in kwacha?',
      },
    ],
    smaller: [
      'More Acts and judgments, plus pending Bills. Levy says plainly when something is still a Bill and not yet law.',
      'A thumbs up and down under every answer, with a box to say what went wrong.',
      'Long answers are no longer cut off, and a second provider takes over if the first is unavailable.',
      'Anyone can try Levy with a few free questions before making an account.',
    ],
  },
]

export function getUpdate(slug: string): Update | null {
  return updates.find((u) => u.slug === slug) ?? null
}

/** "18 November 2026", the way dates are written in Zambia. */
export function longDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
  return `${d} ${months[m - 1]} ${y}`
}
