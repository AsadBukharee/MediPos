import { Pressable, ScrollView, Text } from 'react-native';

import { Button, Card, Empty, text } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { space } from '@/lib/theme';

export default function BranchScreen() {
  const { user, chooseBranch, signOut } = useAuth();
  return (
    <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.md }}>
      <Text style={text.muted}>You can work in more than one branch. Stock, alerts and orders are kept separate for each.</Text>
      {user?.branches.map((branch) => (
        <Pressable key={branch.id} accessibilityRole="button" onPress={() => chooseBranch(branch)}>
          <Card>
            <Text style={text.heading}>{branch.name}</Text>
            <Text style={text.muted}>{branch.code.toUpperCase()}</Text>
          </Card>
        </Pressable>
      ))}
      {user?.branches.length === 0 && <Empty text="Your account has no branch yet. Ask an owner to assign one." />}
      <Button title="Sign out" variant="ghost" onPress={signOut} />
    </ScrollView>
  );
}
