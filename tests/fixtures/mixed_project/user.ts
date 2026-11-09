export class UserService {
  validate(u: { name?: string; age?: number }): boolean {
    if (!u.name) return false;
    if (u.age !== undefined && (u.age < 0 || u.age > 150)) return false;
    return true;
  }
}
