import { useRouter } from 'expo-router';
import { useState } from 'react';
import { FlatList, Pressable, Text, TextInput, View } from 'react-native';

import { Badge, Empty, Notice, OfflineBanner, text } from '@/components/ui';
import { formatDate, formatMoney, useDebounced, useResource } from '@/lib/hooks';
import { colors, radius, space } from '@/lib/theme';
import type { Paginated, StockRow } from '@/lib/types';

const STATE = { ok: { label: 'In stock', tone: 'ok' }, low: { label: 'Low', tone: 'warn' }, out: { label: 'Out', tone: 'danger' } } as const;

export default function SearchScreen() {
  const router = useRouter();
  const [term, setTerm] = useState('');
  const search = useDebounced(term.trim());
  const stock = useResource<Paginated<StockRow>>('/inventory/stock/', { search, is_active: true, page_size: 40 });

  return (
    <FlatList
      data={stock.data?.results ?? []}
      keyExtractor={(row) => String(row.id)}
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={{ padding: space.lg, gap: space.sm }}
      ListHeaderComponent={
        <View style={{ gap: space.md, marginBottom: space.sm }}>
          <TextInput
            accessibilityLabel="Search medicines"
            value={term}
            onChangeText={setTerm}
            placeholder="Name, generic, SKU or barcode"
            placeholderTextColor={colors.muted}
            autoCorrect={false}
            returnKeyType="search"
            style={{ minHeight: 48, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.line, borderRadius: radius.md, paddingHorizontal: space.md, fontSize: 16, color: colors.ink }}
          />
          <OfflineBanner stale={stock.stale} savedAt={stock.savedAt} />
          <Notice text={stock.error} />
        </View>
      }
      renderItem={({ item }) => (
        <Pressable
          accessibilityRole="button"
          onPress={() => router.push({ pathname: '/product/[id]', params: { id: String(item.id), name: `${item.name} ${item.strength}` } })}
          style={{ backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.line, padding: space.md, gap: 2 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: space.sm }}>
            <Text style={[text.heading, { flex: 1 }]}>
              {item.name} <Text style={{ fontWeight: '400', color: colors.muted }}>{item.strength}</Text>
            </Text>
            <Badge label={STATE[item.state].label} tone={STATE[item.state].tone} />
          </View>
          <Text style={text.muted}>
            {item.sellable} {item.base_unit_name.toLowerCase()}(s) sellable · {formatMoney(item.retail_price)} each
            {item.nearest_expiry ? ` · next expiry ${formatDate(item.nearest_expiry)}` : ''}
          </Text>
        </Pressable>
      )}
      ListEmptyComponent={stock.loading || stock.error ? undefined : <Empty text="No medicine matches." />}
    />
  );
}
