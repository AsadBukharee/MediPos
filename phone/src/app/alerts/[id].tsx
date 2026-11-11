import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ScrollView } from 'react-native';

import { AlertCard } from '@/components/alert-card';
import { Button, Notice, OfflineBanner } from '@/components/ui';
import { api } from '@/lib/api';
import { useResource } from '@/lib/hooks';
import { space } from '@/lib/theme';
import type { StockAlert } from '@/lib/types';

/** Opened from a push notification. `action=skip` comes from the notification's Skip button. */
export default function AlertScreen() {
  const { id, action } = useLocalSearchParams<{ id: string; action?: string }>();
  const router = useRouter();
  const alert = useResource<StockAlert>(`/notifications/alerts/${id}/`);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const handled = useRef(false);
  const reload = alert.reload;

  useEffect(() => {
    if (action !== 'skip' || handled.current) return;
    handled.current = true;
    api(`/notifications/alerts/${id}/skip/`, { method: 'POST' })
      .then(() => {
        setMessage('Skipped. You can still add it to the order list below.');
        reload();
      })
      .catch((e: Error) => setError(e.message));
  }, [action, id, reload]);

  return (
    <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.md }} keyboardShouldPersistTaps="handled">
      <OfflineBanner stale={alert.stale} savedAt={alert.savedAt} />
      <Notice text={error ?? alert.error} />
      <Notice tone="ok" text={message} />
      {action === 'add' && alert.data?.status === 'open' && <Notice tone="warn" text="Check the quantity, then add it to the order list." />}
      {alert.data && (
        <AlertCard
          key={`${alert.data.id}-${alert.data.status}-${alert.data.requested_quantity}`}
          alert={alert.data}
          onChanged={(updated) => {
            setMessage(updated.status === 'added' ? `Added to the order list: ${updated.requested_quantity}.` : 'Skipped.');
            reload();
          }}
        />
      )}
      <Button title="Open the order list" variant="secondary" onPress={() => router.replace('/orders')} />
    </ScrollView>
  );
}
