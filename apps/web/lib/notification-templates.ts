import templatesJson from "@/templates/notifications.json";

export type NotificationChannel = "sms" | "push" | "radio" | "email";

export type NotificationTemplate = {
  id: string;
  label: string;
  tool: string;
  gated: boolean;
  channels: NotificationChannel[];
  max_length: number;
  subject: string;
  body: string;
  sample_vars: Record<string, string>;
};

export type RenderedNotification = {
  subject: string;
  body: string;
  length: number;
  overLimit: boolean;
};

const catalog = templatesJson as unknown as {
  schema_version: string;
  templates: NotificationTemplate[];
};

export const notificationTemplates = catalog.templates;

const byId = new Map(notificationTemplates.map((t) => [t.id, t]));

export function templateById(id: string) {
  return byId.get(id);
}

/** Simple {{var}} substitution — matches T3 notify_crew message assembly. */
export function renderTemplate(
  text: string,
  vars: Record<string, string>,
): string {
  return text.replace(/\{\{(\w+)\}\}/g, (_, key: string) => vars[key] ?? `{{${key}}}`);
}

export function renderNotification(
  template: NotificationTemplate,
  vars: Record<string, string>,
): RenderedNotification {
  const subject = renderTemplate(template.subject, vars);
  const body = renderTemplate(template.body, vars);
  const length = body.length;
  return {
    subject,
    body,
    length,
    overLimit: length > template.max_length,
  };
}

export const CHANNEL_LABEL: Record<NotificationChannel, string> = {
  sms: "SMS",
  push: "Push",
  radio: "Radio",
  email: "Email",
};
