import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { RefreshControl, ScrollView, Text, TextInput, View } from 'react-native';

import { Badge, Button, Card, Empty, Notice, OfflineBanner, text } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useAction, useResource } from '@/lib/hooks';
import { colors, radius, space } from '@/lib/theme';
import type { Paginated, Requisition, RequisitionItem } from '@/lib/types';

export default function OrdersScreen() {
  const { can } = useAuth();
  const current = useResource<Requisition>('/purchases/requisitions/current/');
  const pending = useResource<Paginated<Requisition>>('/purchases/requisitions/', { status: 'pending' });
  const { busy, error, run } = useAction();
  const [done, setDone] = useState<string | null>(null);
  const reloadCurrent = current.reload;
  const reloadPending = pending.reload;
  const reload = useCallback(() => {
    reloadCurrent();
    reloadPending();
  }, [reloadCurrent, reloadPending]);
  useFocusEffect(reload);

  const act = async (action: () => Promise<unknown>, message?: string) => {
    const result = await run(action);
    if (result !== undefined || message) setDone(message ?? null);
    reload();
  };
  const list = current.data;
  const editable = can('requisitions.manage');

  return (
    <ScrollView
      contentContainerStyle={{ padding: space.lg, gap: space.md }}
      keyboardShouldPersistTaps="handled"
      refreshControl={<RefreshControl refreshing={current.loading} onRefresh={reload} tintColor={colors.brand} />}>
      <OfflineBanner stale={current.stale} savedAt={current.savedAt} />
      <Notice text={error ?? current.error} />
      <Notice tone="ok" text={done} />

      <Text style={text.heading}>Open order list {list?.number ? `· ${list.number}` : ''}</Text>
      {(list?.items ?? []).map((item) => (
        <OrderLine key={`${item.id}-${item.quantity}`} item={item} editable={editable && !current.stale} onAct={act} />
      ))}
      {!current.loading && (list?.items.length ?? 0) === 0 && <Empty text="The order list is empty. Add medicines from the Alerts tab." />}
      {list?.id && list.items.length > 0 && editable && (
        <Button
          title="Send for approval"
          busy={busy}
          disabled={current.stale}
          onPress={() => act(() => api(`/purchases/requisitions/${list.id}/submit/`, { method: 'POST' }), 'Sent to the manager for approval.')}
        />
      )}

      {(pending.data?.results.length ?? 0) > 0 && <Text style={[text.heading, { marginTop: space.lg }]}>Waiting for approval</Text>}
      {pending.data?.results.map((requisition) => (
        <Card key={requisition.id}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={text.heading}>{requisition.number}</Text>
            <Badge label="Pending" tone="warn" />
          </View>
          {requisition.items.map((item) => (
            <Text key={item.id} style={text.muted}>
              {item.product_name} × {item.quantity}
              {item.supplier_name ? ` · ${item.supplier_name}` : ''}
            </Text>
          ))}
          {can('purchases.approve') && (
            <View style={{ flexDirection: 'row', gap: space.sm, marginTop: space.sm }}>
              <View style={{ flex: 1 }}>
                <Button title="Approve" busy={busy} onPress={() => act(() => api(`/purchases/requisitions/${requisition.id}/approve/`, { method: 'POST' }), `${requisition.number} approved. Create the purchase orders on the web.`)} />
              </View>
              <View style={{ flex: 1 }}>
                <Button title="Reject" variant="secondary" disabled={busy} onPress={() => act(() => api(`/purchases/requisitions/${requisition.id}/reject/`, { method: 'POST' }))} />
              </View>
            </View>
          )}
        </Card>
      ))}
    </ScrollView>
  );
}

function OrderLine({ item, editable, onAct }: { item: RequisitionItem; editable: boolean; onAct: (action: () => Promise<unknown>) => void }) {
  const [quantity, setQuantity] = useState(String(item.quantity));
  const save = () => {
    const value = Number(quantity);
    if (value > 0 && value !== item.quantity) onAct(() => api(`/purchases/requisitions/items/${item.id}/`, { method: 'PATCH', body: { quantity: value } }));
    else setQuantity(String(item.quantity));
  };
  return (
    <Card>
      <Text style={text.heading}>{item.product_name}</Text>
      <Text style={text.muted}>
        {item.supplier_name || 'No supplier chosen'} · requested by {item.requested_by_name}
      </Text>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm }}>
        <TextInput
          accessibilityLabel={`Quantity of ${item.product_name}`}
          value={quantity}
          editable={editable}
          onChangeText={(value) => setQuantity(value.replace(/\D/g, ''))}
          onEndEditing={save}
          keyboardType="number-pad"
          inputMode="numeric"
          style={{ flex: 1, minHeight: 48, borderWidth: 1, borderColor: colors.line, borderRadius: radius.md, paddingHorizontal: space.md, fontSize: 16, color: colors.ink, backgroundColor: editable ? colors.surface : colors.canvas }}
        />
        {editable && <Button title="Remove" variant="ghost" compact onPress={() => onAct(() => api(`/purchases/requisitions/items/${item.id}/`, { method: 'DELETE' }))} />}
      </View>
    </Card>
  );
}
