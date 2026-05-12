const EMAIL_RE = /^([a-zA-Z0-9_\.\-]+)+@([a-zA-Z0-9_\.\-]+)+\.([a-zA-Z]{2,5})+$/;

export function isValidEmail(input: string): boolean {
  return EMAIL_RE.test(input);
}

export default isValidEmail;
