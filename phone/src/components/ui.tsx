import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View, type TextInputProps, type ViewProps } from 'react-native';

import { colors, radius, space } from '@/lib/theme';

type Tone = 'neutral' | 'ok' | 'warn' | 'danger' | 'brand';

const TONES: Record<Tone, { bg: string; fg: string }> = {
  neutral: { bg: colors.canvas, fg: colors.muted },
  ok: { bg: colors.okSoft, fg: colors.ok },
  warn: { bg: colors.warnSoft, fg: colors.warn },
  danger: { bg: colors.dangerSoft, fg: colors.danger },
  brand: { bg: colors.brandSoft, fg: colors.brand },
};

export function Button({
  title,
  onPress,
  variant = 'primary',
  disabled,
  busy,
  compact,
}: {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  disabled?: boolean;
  busy?: boolean;
  compact?: boolean;
}) {
  const palette = {
    primary: { bg: colors.brand, fg: colors.white, border: colors.brand },
    secondary: { bg: colors.surface, fg: colors.ink, border: colors.line },
    ghost: { bg: 'transparent', fg: colors.muted, border: 'transparent' },
    danger: { bg: colors.danger, fg: colors.white, border: colors.danger },
  }[variant];
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || busy, busy }}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        compact && styles.buttonCompact,
        { backgroundColor: palette.bg, borderColor: palette.border, opacity: disabled ? 0.5 : pressed ? 0.8 : 1 },
      ]}>
      {busy ? <ActivityIndicator color={palette.fg} /> : <Text style={[styles.buttonText, { color: palette.fg }]}>{title}</Text>}
    </Pressable>
  );
}

export function Field({ label, ...props }: TextInputProps & { label: string }) {
  return (
    <View style={{ gap: space.xs }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput accessibilityLabel={label} placeholderTextColor={colors.muted} {...props} style={[styles.input, props.style]} />
    </View>
  );
}

export function Card({ style, ...props }: ViewProps) {
  return <View {...props} style={[styles.card, style]} />;
}

export function Badge({ label, tone = 'neutral' }: { label: string; tone?: Tone }) {
  return (
    <View style={[styles.badge, { backgroundColor: TONES[tone].bg }]}>
      <Text style={[styles.badgeText, { color: TONES[tone].fg }]}>{label}</Text>
    </View>
  );
}

export function Notice({ text, tone = 'danger' }: { text?: string | null; tone?: 'danger' | 'warn' | 'ok' }) {
  if (!text) return null;
  return (
    <View accessibilityRole="alert" style={[styles.notice, { backgroundColor: TONES[tone].bg }]}>
      <Text style={{ color: TONES[tone].fg }}>{text}</Text>
    </View>
  );
}

/** Shown when the screen is displaying the saved offline copy. */
export function OfflineBanner({ stale, savedAt }: { stale: boolean; savedAt?: number }) {
  if (!stale) return null;
  const when = savedAt ? new Date(savedAt).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
  return <Notice tone="warn" text={`Offline — showing saved data${when ? ` from ${when}` : ''}. Changes need a connection.`} />;
}

export function Empty({ text }: { text: string }) {
  return <Text style={styles.empty}>{text}</Text>;
}

export function Row({ label, value, tone }: { label: string; value: string | number; tone?: Tone }) {
  return (
    <View style={styles.row}>
      <Text style={{ color: colors.muted }}>{label}</Text>
      <Text style={[styles.rowValue, tone && { color: TONES[tone].fg }]}>{value}</Text>
    </View>
  );
}

export const text = StyleSheet.create({
  title: { fontSize: 22, fontWeight: '700', color: colors.ink, letterSpacing: -0.3 },
  heading: { fontSize: 16, fontWeight: '600', color: colors.ink },
  body: { fontSize: 15, color: colors.ink },
  muted: { fontSize: 13, color: colors.muted },
});

const styles = StyleSheet.create({
  button: {
    minHeight: 48, // comfortable touch target
    paddingHorizontal: space.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonCompact: { minHeight: 44, paddingHorizontal: space.md },
  buttonText: { fontSize: 15, fontWeight: '600' },
  label: { fontSize: 13, fontWeight: '500', color: colors.muted },
  input: {
    minHeight: 48,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    paddingHorizontal: space.md,
    fontSize: 16,
    color: colors.ink,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.line,
    padding: space.lg,
    gap: space.sm,
  },
  badge: { alignSelf: 'flex-start', borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 2 },
  badgeText: { fontSize: 12, fontWeight: '600' },
  notice: { borderRadius: radius.md, padding: space.md },
  empty: { textAlign: 'center', color: colors.muted, paddingVertical: space.xl * 2, paddingHorizontal: space.xl },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 3 },
  rowValue: { fontSize: 15, fontWeight: '600', color: colors.ink, fontVariant: ['tabular-nums'] },
});
