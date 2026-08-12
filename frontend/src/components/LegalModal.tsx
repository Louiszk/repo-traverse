import React, { useEffect, useRef } from 'react';
import { X, ShieldCheck, FileText } from 'lucide-react';
import { MarkdownRenderer } from './MarkdownRenderer';
import { useOnClickOutside } from '../hooks/useOnClickOutside';

export type LegalDocType = 'privacy' | 'terms';

interface LegalModalProps {
  isOpen: boolean;
  activeTab: LegalDocType;
  onClose: () => void;
  onTabChange: (tab: LegalDocType) => void;
}

// ----------------------------------------------------------------------
// Legal Markdown Contents
// ----------------------------------------------------------------------

const PRIVACY_POLICY_MD = `
## Privacy Policy

**Effective Date:** August 4, 2026  
**Version:** 1.1

This Privacy Policy explains how RepoTraverse ("we", "us") processes information when you use the application. RepoTraverse is an independent project and is not affiliated with, sponsored by, or endorsed by GitHub, Inc., OpenAI, L.L.C., Cloudflare, Inc., or Amazon Web Services, Inc.

**Data Controller:**  
*See Impressum for full entity details.*  
**Privacy contact:** \`info@repo-tools.com\`  
*(We are not required to appoint a Data Protection Officer).*

---

### 1. Information We Process & Legal Basis
We process minimal data to provide the service. Under the GDPR, our legal bases are the performance of a contract (Art. 6(1)(b)) and our legitimate interests in securing our service (Art. 6(1)(f)).
* **GitHub URLs:** Processed to clone and index the requested codebase (Art. 6(1)(b)).
* **Chat Prompts:** Processed to analyze the repository (Art. 6(1)(b)).
* **Connection & Device Data:** We temporarily process your IP address and assign a random, anonymous "Device ID" cookie to enforce rate limits and prevent abuse (Art. 6(1)(f)).

---

### 2. How We Use Information
* To clone the requested public repository and generate an Abstract Syntax Tree (AST) knowledge graph.
* To generate AI-powered answers to your architectural questions.
* To prevent abuse, DDoS attacks, and excessive API usage through IP and device-based rate limiting.
* RepoTraverse does **not** sell your information, use it for advertising, or track you across other websites. Providing your data is necessary to use the service; without it, we cannot process your requests.

---

### 3. Third-Party Service Providers & International Transfers
Information is disclosed only where necessary to operate the service.
* **OpenAI:** We use the OpenAI API to generate chat responses. We explicitly send selected source snippets, graph/tool output, repository architecture metadata, and your user-entered chat prompts to OpenAI (OpenAI OpCo, LLC or OpenAI Ireland Ltd.). We have a Data Processing Addendum (DPA) containing EU Standard Contractual Clauses (SCCs) to legally safeguard international data transfers. Additionally, OpenAI is certified under the EU-US Data Privacy Framework (DPF). OpenAI **does not** use your chat prompts or repository data to train their models. They retain API data for a maximum of 30 days strictly for abuse and misuse monitoring.
* **GitHub, Inc.:** We fetch repository metadata (such as open-source licenses) and clone public repository code directly from GitHub's servers.
* **Cloudflare, Inc.:** We use Cloudflare as a reverse proxy, DNS provider, and Web Application Firewall (WAF) for SSL/TLS termination, DDoS protection, rate limiting, and traffic routing. Cloudflare processes connection data (including your IP address and HTTP request headers) at its edge nodes before forwarding requests to our origin server. Cloudflare is certified under the EU-US Data Privacy Framework (DPF) and uses the European Commission's Standard Contractual Clauses (SCCs) for international data transfers where applicable.
* **Amazon Web Services (AWS):** Our application server is hosted on an AWS EC2 instance (Amazon Web Services EMEA SARL / Amazon.com, Inc.) which runs our backend services and temporary session storage. AWS processes connection data, server request logs, and transient session artifacts required to operate the application. AWS is certified under the EU-US Data Privacy Framework (DPF) and implements EU Standard Contractual Clauses (SCCs) for international data transfers where applicable.

---

### 4. Storage and Retention
* **Cloned Repositories:** Resetting the browser workspace removes local session access but does not immediately delete server-side temporary artifacts, which are removed according to our retention schedule (a maximum of two hours of inactivity, or earlier if storage limits are reached).
* **Server Traces:** Anonymous operational logs (such as token usage and execution times) are kept locally to monitor server costs and health. These are automatically deleted after 60 days, or earlier if server storage thresholds are reached.

---

### 5. Cookies and Browser Storage
RepoTraverse and our infrastructure providers only use strictly necessary cookies required to operate the service and ensure security against abuse, exempt from consent requirements under § 25 (2) TDDDG:
* \`session_secret_<id>\`: A temporary, random session authentication cookie used to protect access to an active repository session against cross-site request forgery (CSRF). It expires after 2 hours of inactivity.
* \`device_id\`: A randomized identifier used solely to enforce daily rate limits and prevent API abuse.
* **Cloudflare Security Cookies:** Cloudflare may issue essential security cookies (such as \`__cf_bm\` or \`cf_clearance\`) to manage bot detection and challenge verified visitors.

---

### 6. Your Choices and Rights
Under the GDPR, you have the right to request access, correction, deletion, or restriction of your personal data, as well as the right to object to processing and lodge a complaint with a supervisory authority. Because we do not maintain user accounts, we may require additional information (such as your IP address or Device ID) to locate any transient data tied to your session. Contact us using the email address above to exercise your rights or request deletion. 

* **Automated Decision-Making:** We do not carry out automated decision-making or profiling with legal or similarly significant effects (Art. 22 GDPR).
* **Children:** We do not knowingly collect data from children under 16.
`;

const TERMS_OF_SERVICE_MD = `
## Terms of Service

**Effective Date:** August 4, 2026  
**Version:** 1.1

These Terms of Service ("Terms") govern your use of RepoTraverse. By using the application, you agree to these Terms. If you do not agree, do not submit a repository or use the chat interface.

---

### 1. The Service & Third-Party Terms
RepoTraverse is a free tool for exploring the architecture of public open-source codebases through AI-powered graph analysis. It is provided "as is" and features depend on the availability and infrastructure of our third-party service providers, including [GitHub](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service), [OpenAI](https://openai.com/policies/terms-of-use), Cloudflare, and Amazon Web Services (AWS). Your use of RepoTraverse is also subject to the applicable terms and policies of these infrastructure providers.

---

### 2. Eligibility and Acceptable Use
* You must be at least **16 years old** to use the service.
* You may use RepoTraverse only for lawful purposes.
* You may only submit URLs for **public** GitHub repositories.
* You must not attempt to bypass our access controls, rate limits, concurrent task limits, or security measures.
* You must not use automated scripts, bots, or scrapers that interfere with the stability of our servers.
* You must not submit malicious prompts designed to exploit the underlying AI models (jailbreaking) or compromise our server infrastructure.

**Enforcement:** We reserve the right to block traffic, cancel queued jobs, delete abusive sessions, retain limited logs necessary for abuse investigation, and cooperate with lawful law enforcement requests without notice if we detect a violation of these Terms.

---

### 3. Repository Content and Licenses
RepoTraverse attempts to limit indexing to public GitHub repositories for which GitHub reports a license in our supported allowlist. This automated check may be incomplete or inaccurate. All code, architecture, and documentation analyzed by the tool remains the copyright of its respective authors. You are solely responsible for ensuring that your use of any code snippets retrieved by RepoTraverse complies with the repository's original open-source license. RepoTraverse claims no ownership over the code analyzed.

---

### 4. AI-Generated Content & Prohibited Data
RepoTraverse uses large language models (LLMs) to analyze code and generate responses.
* **No Guarantees:** AI-generated output may be incomplete, inaccurate, or outdated. You should independently verify any architectural claims, code snippets, or explanations provided by the agent.
* **Confidential Information:** You must not submit confidential, proprietary, or personal data into the chat interface. Any data you submit is transmitted to and processed by our third-party AI providers (e.g., OpenAI). While we strongly warn against submitting sensitive secrets, if you do, they will be processed and logged as part of your query.

---

### 5. Limitation of Liability
To the fullest extent permitted by applicable law, RepoTraverse is provided "as is" and "as available." All implied warranties are disclaimed. We are not liable for any damages, data loss, or copyright disputes arising from your use of the tool or the AI-generated outputs. Nothing in these Terms excludes liability where prohibited by law, including mandatory liability for intent or gross negligence.

---

### 6. Governing Law
These Terms are governed by German law. If you are a consumer within the EU, this choice of law does not deprive you of the protection afforded by mandatory provisions of the law of your country of residence.

---

### 7. Contact & Dispute Resolution
Questions about these Terms can be sent to \`info@repo-tools.com\`.

**Consumer Dispute Resolution (VSBG):** We are exempt from the obligation to declare participation in consumer dispute resolution under § 36(1) No. 1 VSBG due to company size, and we do not participate in such proceedings before a consumer arbitration board voluntarily.
`;

export const LegalModal: React.FC<LegalModalProps> = ({
  isOpen,
  activeTab,
  onClose,
  onTabChange,
}) => {
  const modalRef = useRef<HTMLDivElement>(null);

  useOnClickOutside(modalRef, () => {
    if (isOpen) onClose();
  });

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        ref={modalRef}
        className="panel-bg border rounded-2xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header with Tabs and Close button */}
        <div className="px-6 py-4 border-b flex items-start sm:items-center justify-between gap-4 flex-shrink-0 card-bg">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => onTabChange('privacy')}
              className={`px-3 sm:px-4 py-2 rounded-lg text-xs font-semibold flex items-center gap-2 transition-colors cursor-pointer ${
                activeTab === 'privacy'
                  ? 'accent-btn shadow-sm'
                  : 'dark:text-slate-400 text-slate-600 hover:dark:text-slate-200 hover:text-slate-900 subtle-bg'
              }`}
            >
              <ShieldCheck className="w-4 h-4" />
              <span>Privacy Policy</span>
            </button>

            <button
              type="button"
              onClick={() => onTabChange('terms')}
              className={`px-3 sm:px-4 py-2 rounded-lg text-xs font-semibold flex items-center gap-2 transition-colors cursor-pointer ${
                activeTab === 'terms'
                  ? 'accent-btn shadow-sm'
                  : 'dark:text-slate-400 text-slate-600 hover:dark:text-slate-200 hover:text-slate-900 subtle-bg'
              }`}
            >
              <FileText className="w-4 h-4" />
              <span>Terms of Service</span>
            </button>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg subtle-bg dark:text-slate-400 text-slate-600 hover:dark:text-slate-200 hover:text-slate-900 transition-colors cursor-pointer flex-shrink-0"
            title="Close modal (Esc)"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Content Body */}
        <div className="flex-1 overflow-y-auto p-6 sm:p-8">
          
          {activeTab === 'privacy' && <MarkdownRenderer content={PRIVACY_POLICY_MD} />}
          {activeTab === 'terms' && <MarkdownRenderer content={TERMS_OF_SERVICE_MD} />}

        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t card-bg flex items-center justify-between text-xs text-slate-400 flex-shrink-0">
          <span>RepoTraverse Legal Notice & Legal Info</span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded accent-btn font-semibold text-xs transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
