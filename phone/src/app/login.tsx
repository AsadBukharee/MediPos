import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button, Field, Notice } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { useAction } from '@/lib/hooks';
import { colors, space } from '@/lib/theme';

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const { busy, error, run } = useAction();
  const submit = () => run(() => signIn(username.trim(), password));

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.ink }}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'flex-end' }} keyboardShouldPersistTaps="handled">
          <View style={{ padding: space.xl, gap: space.sm }}>
            <Text style={{ color: colors.white, fontSize: 30, fontWeight: '700', letterSpacing: -0.5 }}>
              Medi<Text style={{ color: '#5FD4C4' }}>Pos</Text>
            </Text>
            <Text style={{ color: '#FFFFFF99', fontSize: 15 }}>Stock alerts, order lists and batch look-up for your pharmacy.</Text>
          </View>
          <View style={{ backgroundColor: colors.canvas, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: space.xl, gap: space.lg }}>
            <Notice text={error} />
            <Field label="Username" value={username} onChangeText={setUsername} autoCapitalize="none" autoCorrect={false} autoComplete="username" textContentType="username" returnKeyType="next" />
            <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry autoComplete="current-password" textContentType="password" returnKeyType="go" onSubmitEditing={submit} />
            <Button title="Sign in" busy={busy} disabled={!username.trim() || !password} onPress={submit} />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
