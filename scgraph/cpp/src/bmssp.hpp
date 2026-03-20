// Copyright (c) 2025 Lucas Castro and Thailsson Clementino
// Licensed under the MIT License.
// SEE: https://github.com/lcs147/bmssp/blob/master/single_include/bmssp.hpp

#ifndef CASTRO_THAILSSON_BMSSP_WC_DUAN25_H
#define CASTRO_THAILSSON_BMSSP_WC_DUAN25_H

#include<set>
#include<map>
#include<list>
#include<cmath>
#include<vector>
#include<utility>
#include<limits>
#include<queue>
#include<algorithm>
/*          Copyright Andrei Alexandrescu, 2016-.
 * Distributed under the Boost Software License, Version 1.0.
 *    (See accompanying file LICENSE_1_0.txt or copy at
 *          https://boost.org/LICENSE_1_0.txt)
 */
/*          Copyright Danila Kutenin, 2020-.
 * Distributed under the Boost Software License, Version 1.0.
 *    (See accompanying file LICENSE_1_0.txt or copy at
 *          https://boost.org/LICENSE_1_0.txt)
 */
// Adjusted from Alexandrescu paper to support arbitrary comparators.

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <functional>
#include <iterator>
#include <utility>

/*          Copyright Andrei Alexandrescu, 2016-,
 * Distributed under the Boost Software License, Version 1.0.
 *    (See accompanying file LICENSE_1_0.txt or copy at
 *          https://boost.org/LICENSE_1_0.txt)
 */
/*          Copyright Danila Kutenin, 2020-.
 * Distributed under the Boost Software License, Version 1.0.
 *    (See accompanying file LICENSE_1_0.txt or copy at
 *          https://boost.org/LICENSE_1_0.txt)
 */

#include <cassert>
#include <iterator>
#include <type_traits>
#include <utility>

namespace miniselect {
namespace median_common_detail {

template <class Compare>
struct CompareRefType {
  // Pass the comparator by lvalue reference. Or in debug mode, using a
  // debugging wrapper that stores a reference.
  using type = typename std::add_lvalue_reference<Compare>::type;
};
/**
Swaps the median of r[a], r[b], and r[c] into r[b].
*/
template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline void median3(Iter r, DiffType a, DiffType b, DiffType c,
                    Compare&& comp) {
  if (comp(r[b], r[a]))  // b < a
  {
    if (comp(r[b], r[c]))  // b < a, b < c
    {
      if (comp(r[c], r[a]))  // b < c < a
        std::swap(r[b], r[c]);
      else  // b < a <= c
        std::swap(r[b], r[a]);
    }
  } else if (comp(r[c], r[b]))  // a <= b, c < b
  {
    if (comp(r[c], r[a]))  // c < a <= b
      std::swap(r[b], r[a]);
    else  // a <= c < b
      std::swap(r[b], r[c]);
  }
}

/**
Sorts in place r[a], r[b], and r[c].
*/
template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline void sort3(Iter r, DiffType a, DiffType b, DiffType c, Compare&& comp) {
  typedef typename std::iterator_traits<Iter>::value_type T;
  if (comp(r[b], r[a]))  // b < a
  {
    if (comp(r[c], r[b]))  // c < b < a
    {
      std::swap(r[a], r[c]);  // a < b < c
    } else                    // b < a, b <= c
    {
      T t = std::move(r[a]);
      r[a] = std::move(r[b]);
      if (comp(r[c], t))  // b <= c < a
      {
        r[b] = std::move(r[c]);
        r[c] = std::move(t);
      } else  // b < a <= c
      {
        r[b] = std::move(t);
      }
    }
  } else if (comp(r[c], r[b]))  // a <= b, c < b
  {
    T t = std::move(r[c]);
    r[c] = std::move(r[b]);
    if (comp(t, r[a]))  // c < a < b
    {
      r[b] = std::move(r[a]);
      r[a] = std::move(t);
    } else  // a <= c < b
    {
      r[b] = std::move(t);
    }
  }

  assert(!comp(r[b], r[a]) && !comp(r[c], r[b]));
}

/**
If leanRight == false, swaps the lower median of r[a]...r[d] into r[b] and
the minimum into r[a]. If leanRight == true, swaps the upper median of
r[a]...r[d] into r[c] and the minimum into r[d].
*/
template <bool leanRight, class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline void partition4(Iter r, DiffType a, DiffType b, DiffType c, DiffType d,
                       Compare&& comp) {
  assert(a != b && a != c && a != d && b != c && b != d && c != d);
  /* static */ if (leanRight) {
    // In the median of 5 algorithm, consider r[e] infinite
    if (comp(r[c], r[a])) {
      std::swap(r[a], r[c]);
    }  // a <= c
    if (comp(r[d], r[b])) {
      std::swap(r[b], r[d]);
    }  // a <= c, b <= d
    if (comp(r[d], r[c])) {
      std::swap(r[c], r[d]);  // a <= d, b <= c < d
      std::swap(r[a], r[b]);  // b <= d, a <= c < d
    }                         // a <= c <= d, b <= d
    if (comp(r[c], r[b])) {   // a <= c <= d, c < b <= d
      std::swap(r[b], r[c]);  // a <= b <= c <= d
    }                         // a <= b <= c <= d
  } else {
    // In the median of 5 algorithm consider r[a] infinitely small, then
    // change b->a. c->b, d->c, e->d
    if (comp(r[c], r[a])) {
      std::swap(r[a], r[c]);
    }
    if (comp(r[c], r[b])) {
      std::swap(r[b], r[c]);
    }
    if (comp(r[d], r[a])) {
      std::swap(r[a], r[d]);
    }
    if (comp(r[d], r[b])) {
      std::swap(r[b], r[d]);
    } else {
      if (comp(r[b], r[a])) {
        std::swap(r[a], r[b]);
      }
    }
  }
}

/**
Places the median of r[a]...r[e] in r[c] and partitions the other elements
around it.
*/
template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline void partition5(Iter r, DiffType a, DiffType b, DiffType c, DiffType d,
                       DiffType e, Compare&& comp) {
  assert(a != b && a != c && a != d && a != e && b != c && b != d && b != e &&
         c != d && c != e && d != e);
  if (comp(r[c], r[a])) {
    std::swap(r[a], r[c]);
  }
  if (comp(r[d], r[b])) {
    std::swap(r[b], r[d]);
  }
  if (comp(r[d], r[c])) {
    std::swap(r[c], r[d]);
    std::swap(r[a], r[b]);
  }
  if (comp(r[e], r[b])) {
    std::swap(r[b], r[e]);
  }
  if (comp(r[e], r[c])) {
    std::swap(r[c], r[e]);
    if (comp(r[c], r[a])) {
      std::swap(r[a], r[c]);
    }
  } else {
    if (comp(r[c], r[b])) {
      std::swap(r[b], r[c]);
    }
  }
}

/**
Implements Hoare partition.
*/
template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline Iter pivot_partition(Iter r, DiffType k, DiffType length,
                            Compare&& comp) {
  assert(k < length);
  std::swap(*r, r[k]);
  DiffType lo = 1, hi = length - 1;
  for (;; ++lo, --hi) {
    for (;; ++lo) {
      if (lo > hi) goto loop_done;
      if (!comp(r[lo], *r)) break;
    }
    // found the left bound:  r[lo] >= r[0]
    assert(lo <= hi);
    for (; comp(*r, r[hi]); --hi) {
    }
    if (lo >= hi) break;
    // found the right bound: r[hi] <= r[0], swap & make progress
    std::swap(r[lo], r[hi]);
  }
loop_done:
  --lo;
  std::swap(r[lo], *r);
  return r + lo;
}

/**
Implements the quickselect algorithm, parameterized with a partition function.
*/
template <class Iter, class Compare, Iter (*partition)(Iter, Iter, Compare)>
inline void quickselect(Iter r, Iter mid, Iter end, Compare&& comp) {
  if (r == end || mid >= end) return;
  assert(r <= mid && mid < end);
  for (;;) switch (end - r) {
      case 1:
        return;
      case 2:
        if (comp(r[1], *r)) std::swap(*r, r[1]);
        return;
      case 3:
        sort3(r, 0, 1, 2, comp);
        return;
      case 4:
        switch (mid - r) {
          case 0:
            goto select_min;
          case 1:
            partition4<false>(r, 0, 1, 2, 3, comp);
            break;
          case 2:
            partition4<true>(r, 0, 1, 2, 3, comp);
            break;
          case 3:
            goto select_max;
          default:
            assert(false);
        }
        return;
      default:
        assert(end - r > 4);
        if (r == mid) {
        select_min:
          auto pivot = r;
          for (++mid; mid < end; ++mid)
            if (comp(*mid, *pivot)) pivot = mid;
          std::swap(*r, *pivot);
          return;
        }
        if (mid + 1 == end) {
        select_max:
          auto pivot = r;
          for (mid = r + 1; mid < end; ++mid)
            if (comp(*pivot, *mid)) pivot = mid;
          std::swap(*pivot, *(end - 1));
          return;
        }
        auto pivot = partition(r, end, comp);
        if (pivot == mid) return;
        if (mid < pivot) {
          end = pivot;
        } else {
          r = pivot + 1;
        }
    }
}

/**
Returns the index of the median of r[a], r[b], and r[c] without writing
anything.
*/
template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline DiffType median_index(const Iter r, DiffType a, DiffType b, DiffType c,
                             Compare&& comp) {
  if (comp(r[c], r[a])) std::swap(a, c);
  if (comp(r[c], r[b])) return c;
  if (comp(r[b], r[a])) return a;
  return b;
}

/**
Returns the index of the median of r[a], r[b], r[c], and r[d] without writing
anything. If leanRight is true, computes the upper median. Otherwise, conputes
the lower median.
*/
template <bool leanRight, class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline DiffType median_index(Iter r, DiffType a, DiffType b, DiffType c,
                             DiffType d, Compare&& comp) {
  if (comp(r[d], r[c])) std::swap(c, d);
  if (leanRight) {
    if (comp(r[c], r[a])) {
      assert(comp(r[c], r[a]) && !comp(r[d], r[c]));  // so r[c]) is out
      return median_index(r, a, b, d, comp);
    }
  } else {
    if (!comp(r[d], r[a])) {
      return median_index(r, a, b, c, comp);
    }
  }
  // Could return median_index(r, b, c, d) but we already know r[c] <= r[d]
  if (!comp(r[c], r[b])) return c;
  if (comp(r[d], r[b])) return d;
  return b;
}

/**
Tukey's Ninther: compute the median of r[_1], r[_2], r[_3], then the median of
r[_4], r[_5], r[_6], then the median of r[_7], r[_8], r[_9], and then swap the
median of those three medians into r[_5].
*/
template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline void ninther(Iter r, DiffType _1, DiffType _2, DiffType _3, DiffType _4,
                    DiffType _5, DiffType _6, DiffType _7, DiffType _8,
                    DiffType _9, Compare&& comp) {
  _2 = median_index(r, _1, _2, _3, comp);
  _8 = median_index(r, _7, _8, _9, comp);
  if (comp(r[_8], r[_2])) std::swap(_2, _8);
  if (comp(r[_6], r[_4])) std::swap(_4, _6);
  // Here we know that r[_2] and r[_8] are the other two medians and that
  // r[_2] <= r[_8]. We also know that r[_4] <= r[_6]
  if (comp(r[_5], r[_4])) {
    // r[_4] is the median of r[_4], r[_5], r[_6]
  } else if (comp(r[_6], r[_5])) {
    // r[_6] is the median of r[_4], r[_5], r[_6]
    _4 = _6;
  } else {
    // Here we know r[_5] is the median of r[_4], r[_5], r[_6]
    if (comp(r[_5], r[_2])) return std::swap(r[_5], r[_2]);
    if (comp(r[_8], r[_5])) return std::swap(r[_5], r[_8]);
    // This is the only path that returns with no swap
    return;
  }
  // Here we know r[_4] is the median of r[_4], r[_5], r[_6]
  if (comp(r[_4], r[_2]))
    _4 = _2;
  else if (comp(r[_8], r[_4]))
    _4 = _8;
  std::swap(r[_5], r[_4]);
}

/**
Input assumptions:
(a) hi <= rite
(c) the range r[0 .. hi] contains elements no smaller than r[0]
Output guarantee: same as Hoare partition using r[0] as pivot. Returns the new
position of the pivot.
*/
template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline DiffType expand_partition_right(Iter r, DiffType hi, DiffType rite,
                                       Compare&& comp) {
  DiffType pivot = 0;
  assert(pivot <= hi);
  assert(hi <= rite);
  // First loop: spend r[pivot .. hi]
  for (; pivot < hi; --rite) {
    if (rite == hi) goto done;
    if (!comp(r[rite], r[0])) continue;
    ++pivot;
    std::swap(r[rite], r[pivot]);
  }
  // Second loop: make left and pivot meet
  for (; rite > pivot; --rite) {
    if (!comp(r[rite], r[0])) continue;
    while (rite > pivot) {
      ++pivot;
      if (comp(r[0], r[pivot])) {
        std::swap(r[rite], r[pivot]);
        break;
      }
    }
  }

done:
  std::swap(r[0], r[pivot]);
  return pivot;
}

/**
Input assumptions:
(a) lo > 0, lo <= pivot
(b) the range r[lo .. pivot] already contains elements no greater than r[pivot]
Output guarantee: Same as Hoare partition around r[pivot]. Returns the new
position of the pivot.
*/
template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline DiffType expand_partition_left(Iter r, DiffType lo, DiffType pivot,
                                      Compare&& comp) {
  assert(lo > 0 && lo <= pivot);
  DiffType left = 0;
  const auto oldPivot = pivot;
  for (; lo < pivot; ++left) {
    if (left == lo) goto done;
    if (!comp(r[oldPivot], r[left])) continue;
    --pivot;
    std::swap(r[left], r[pivot]);
  }
  // Second loop: make left and pivot meet
  for (;; ++left) {
    if (left == pivot) break;
    if (!comp(r[oldPivot], r[left])) continue;
    for (;;) {
      if (left == pivot) goto done;
      --pivot;
      if (comp(r[pivot], r[oldPivot])) {
        std::swap(r[left], r[pivot]);
        break;
      }
    }
  }

done:
  std::swap(r[oldPivot], r[pivot]);
  return pivot;
}

/**
Input assumptions:
(a) lo <= pivot, pivot < hi, hi <= length
(b) the range r[lo .. pivot] already contains elements no greater than
r[pivot]
(c) the range r[pivot .. hi] already contains elements no smaller than
r[pivot]
Output guarantee: Same as Hoare partition around r[pivot], returning the new
position of the pivot.
*/
template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline DiffType expand_partition(Iter r, DiffType lo, DiffType pivot,
                                 DiffType hi, DiffType length, Compare&& comp) {
  assert(lo <= pivot && pivot < hi && hi <= length);
  --hi;
  --length;
  DiffType left = 0;
  for (;; ++left, --length) {
    for (;; ++left) {
      if (left == lo)
        return pivot + expand_partition_right(r + pivot, hi - pivot,
                                              length - pivot, comp);
      if (comp(r[pivot], r[left])) break;
    }
    for (;; --length) {
      if (length == hi)
        return left +
               expand_partition_left(r + left, lo - left, pivot - left, comp);
      if (!comp(r[pivot], r[length])) break;
    }
    std::swap(r[left], r[length]);
  }
}

}  // namespace median_common_detail
}  // namespace miniselect

namespace miniselect {
namespace median_of_ninthers_detail {

template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
void adaptive_quickselect(Iter r, DiffType n, DiffType length, Compare&& comp);

/**
Median of minima
*/
template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline DiffType median_of_minima(Iter const r, const DiffType n,
                                 const DiffType length, Compare&& comp) {
  assert(length >= 2);
  assert(n <= length / 6);
  assert(n > 0);
  const DiffType subset = n * 2, computeMinOver = (length - subset) / subset;
  assert(computeMinOver > 0);
  for (DiffType i = 0, j = subset; i < subset; ++i) {
    const DiffType limit = j + computeMinOver;
    DiffType minIndex = j;
    while (++j < limit)
      if (comp(r[j], r[minIndex])) minIndex = j;
    if (comp(r[minIndex], r[i])) std::swap(r[i], r[minIndex]);
    assert(j < length || i + 1 == subset);
  }
  adaptive_quickselect(r, n, subset, comp);
  return median_common_detail::expand_partition(r, DiffType{0}, n, subset,
                                                length, comp);
}

/**
Median of maxima
*/
template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline DiffType median_of_maxima(Iter const r, const DiffType n,
                                 const DiffType length, Compare&& comp) {
  assert(length >= 2);
  assert(n < length && n / 5 >= length - n);
  const DiffType subset = (length - n) * 2, subsetStart = length - subset,
                 computeMaxOver = subsetStart / subset;
  assert(computeMaxOver > 0);
  for (DiffType i = subsetStart, j = i - subset * computeMaxOver; i < length;
       ++i) {
    const DiffType limit = j + computeMaxOver;
    DiffType maxIndex = j;
    while (++j < limit)
      if (comp(r[maxIndex], r[j])) maxIndex = j;
    if (comp(r[i], r[maxIndex])) std::swap(r[i], r[maxIndex]);
    assert(j != 0 || i + 1 == length);
  }
  adaptive_quickselect(r + subsetStart, static_cast<DiffType>(length - n),
                       subset, comp);
  return median_common_detail::expand_partition(r, subsetStart, n, length,
                                                length, comp);
}

/**
Partitions r[0 .. length] using a pivot of its own choosing. Attempts to pick a
pivot that approximates the median. Returns the position of the pivot.
*/
template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline DiffType median_of_ninthers(Iter const r, const DiffType length,
                                   Compare&& comp) {
  assert(length >= 12);
  const DiffType frac = length <= 1024         ? length / 12
                        : length <= 128 * 1024 ? length / 64
                                               : length / 1024;
  DiffType pivot = frac / 2;
  const DiffType lo = length / 2 - pivot, hi = lo + frac;
  assert(lo >= frac * 4);
  assert(length - hi >= frac * 4);
  assert(lo / 2 >= pivot);
  const DiffType gap = (length - 9 * frac) / 4;
  DiffType a = lo - 4 * frac - gap, b = hi + gap;
  for (DiffType i = lo; i < hi; ++i, a += 3, b += 3) {
    median_common_detail::ninther(
        r, a, static_cast<DiffType>(i - frac), b, static_cast<DiffType>(a + 1),
        i, static_cast<DiffType>(b + 1), static_cast<DiffType>(a + 2),
        static_cast<DiffType>(i + frac), static_cast<DiffType>(b + 2), comp);
  }

  adaptive_quickselect(r + lo, pivot, frac, comp);
  return median_common_detail::expand_partition(
      r, lo, static_cast<DiffType>(lo + pivot), hi, length, comp);
}

/**
Quickselect driver for median_of_ninthers, median_of_minima, and
median_of_maxima. Dispathes to each depending on the relationship between n (the
sought order statistics) and length.
*/
template <class Iter, class Compare, class DiffType>
inline void adaptive_quickselect(Iter r, DiffType n, DiffType length,
                                 Compare&& comp) {
  assert(n < length);
  for (;;) {
    // Decide strategy for partitioning
    if (n == 0) {
      // That would be the max
      DiffType pivot = n;
      for (++n; n < length; ++n)
        if (comp(r[n], r[pivot])) pivot = n;
      std::swap(r[0], r[pivot]);
      return;
    }
    if (n + 1 == length) {
      // That would be the min
      DiffType pivot = 0;
      for (n = 1; n < length; ++n)
        if (comp(r[pivot], r[n])) pivot = n;
      std::swap(r[pivot], r[length - 1]);
      return;
    }
    assert(n < length);
    DiffType pivot;
    if (length <= 16)
      pivot = median_common_detail::pivot_partition(r, n, length, comp) - r;
    else if (n <= length / 6)
      pivot = median_of_minima(r, n, length, comp);
    else if (n / 5 >= length - n)
      pivot = median_of_maxima(r, n, length, comp);
    else
      pivot = median_of_ninthers(r, length, comp);

    // See how the pivot fares
    if (pivot == n) {
      return;
    }
    if (pivot > n) {
      length = pivot;
    } else {
      ++pivot;
      r += pivot;
      length -= pivot;
      n -= pivot;
    }
  }
}

}  // namespace median_of_ninthers_detail

template <class Iter, class Compare>
inline void median_of_ninthers_select(Iter begin, Iter mid, Iter end,
                                      Compare comp) {
  if (mid == end) return;
  using CompType = typename median_common_detail::CompareRefType<Compare>::type;

  median_of_ninthers_detail::adaptive_quickselect<Iter, CompType>(
      begin, mid - begin, end - begin, comp);
}

template <class Iter>
inline void median_of_ninthers_select(Iter begin, Iter mid, Iter end) {
  using T = typename std::iterator_traits<Iter>::value_type;
  median_of_ninthers_select(begin, mid, end, std::less<T>());
}

template <class Iter, class Compare>
inline void median_of_ninthers_partial_sort(Iter begin, Iter mid, Iter end,
                                            Compare comp) {
  if (begin == mid) return;
  using CompType = typename median_common_detail::CompareRefType<Compare>::type;
  using DiffType = typename std::iterator_traits<Iter>::difference_type;

  median_of_ninthers_detail::adaptive_quickselect<Iter, CompType>(
      begin, static_cast<DiffType>(mid - begin - 1), end - begin, comp);
  std::sort<Iter, CompType>(begin, mid, comp);
}

template <class Iter>
inline void median_of_ninthers_partial_sort(Iter begin, Iter mid, Iter end) {
  typedef typename std::iterator_traits<Iter>::value_type T;
  median_of_ninthers_partial_sort(begin, mid, end, std::less<T>());
}

}  // namespace miniselect

namespace spp {

template<typename dataT>
struct worst_case_hash_map {
    int counter = 1;
    std::vector<int> flag;
    std::vector<std::pair<int, dataT>> data;
    worst_case_hash_map(int n): data(n), flag(n) {}; // O(n)

    void erase(int id) { // O(1)
        flag[id] = counter - 1;
    }
    dataT& operator[](int id) { // O(1)
        flag[id] = counter;
        data[id].first = id;
        return data[id].second;
    }
    std::vector<std::pair<int, dataT>>::iterator find(int id) { // O(1)
        if(flag[id] != counter) return data.end();
        return data.begin() + id;
    }
    std::vector<std::pair<int, dataT>>::iterator end() { return data.end(); } // O(1)

    void clear() { counter++; } // O(1)
};

template<typename uniqueDistT>
class batchPQ { // batch priority queue, implemented as in Lemma 3.3

    template<typename V>
    using hash_map = worst_case_hash_map<V>;

    using elementT = std::pair<int,uniqueDistT>;
    
    struct CompareUB {
        template <typename It>
        bool operator()(const std::pair<uniqueDistT, It>& a, const std::pair<uniqueDistT, It>& b) const {
            if (a.first != b.first) return a.first < b.first;
            return  addressof(*a.second) < addressof(*b.second);
        }
    };
    
    typename std::list<std::list<elementT>>::iterator it_min;
    
    std::list<std::list<elementT>> D0,D1;
    std::set<std::pair<uniqueDistT,typename std::list<std::list<elementT>>::iterator>,CompareUB> UBs;
    
    int M,size_;
    uniqueDistT B;
    
    hash_map<uniqueDistT> actual_value;
    hash_map<std::pair<typename std::list<std::list<elementT>>::iterator, typename std::list<elementT>::iterator>> where_is0, where_is1;
    
public:

    batchPQ(int n): actual_value(n), where_is0(n), where_is1(n){} // O(n)

    void initialize(int M_, uniqueDistT B_) { // O(1)
        M = M_; B = B_;
        D0 = {};
        D1 = {std::list<elementT>()};
        UBs = {make_pair(B_,D1.begin())};
        size_ = 0;

        actual_value.clear();
        where_is0.clear(); where_is1.clear();
    }

    int size(){
        return size_;
    }
    
    void insert(uniqueDistT x){ // O(lg(Block Numbers))         
        uniqueDistT b = x;
        int a = get<2>(b);
    
        // checking if exists
        auto it_exist = actual_value.find(a);
        int exist = (it_exist != actual_value.end()); 
    
        if(exist && it_exist->second > b){
            delete_(x);
        }else if(exist){
            return;
        }
        
        // Searching for the first block with UB which is > 
        auto it_UB_block = UBs.lower_bound({b,it_min});
        auto [ub,it_block] = (*it_UB_block);
        
        // Inserting key/value (a,b)
        auto it = it_block->insert(it_block->end(),{a,b});
        where_is1[a] = {it_block, it};
        actual_value[a] = b;
    
        size_++;
    
        // Checking if exceeds the sixe limit M
        if((*it_block).size() > M){
            split(it_block);
        }
    }
    
    void batchPrepend(const std::vector<uniqueDistT> &v){
        std::list<elementT> l;
        for(auto x: v){
            l.push_back({get<2>(x),x});
        }
        batchPrepend(l);
    }

    std::pair<uniqueDistT, std::vector<int>> pull(){ // O(M)
        std::vector<elementT> s0,s1;
        s0.reserve(2 * M); s1.reserve(M);
    
        auto it_block = D0.begin();
        while(it_block != D0.end() && s0.size() <= M){ // O(M)   
            for (const auto& x : *it_block) s0.push_back(x);
            it_block++;
        }
    
        it_block = D1.begin();
        while(it_block != D1.end() && s1.size() <= M){   //O(M)
            for (const auto& x : *it_block) s1.push_back(x);
            it_block++;
        }
    
        if(s1.size() + s0.size() <= M){
            std::vector<int> ret;
            ret.reserve(s1.size()+s0.size());
            for(auto [a,b] : s0) {
                ret.push_back(a);
                delete_({b});
            }
            for(auto [a,b] : s1){
                ret.push_back(a);
                delete_({b});
            } 
            
            return {B, ret};
        }else{  
            std::vector<elementT> &l = s0;
            l.insert(l.end(), s1.begin(), s1.end());

            uniqueDistT med = selectKth(l, M);
            std::vector<int> ret;
            ret.reserve(M);
            for(auto [a,b]: l){
                if(b < med) {
                    ret.push_back(a);
                    delete_({b});
                }
            }
            return {med,ret};
        }
    }
    inline void erase(int key) {
        if(actual_value.find(key) != actual_value.end())
            delete_({-1, -1, key, -1});
    }
    
private:
    void delete_(uniqueDistT x){    
        int a = get<2>(x);
        uniqueDistT b = actual_value[a];
        
        auto it_w = where_is1.find(a);
        if((it_w != where_is1.end())){
            auto [it_block,it] = it_w->second;
            
            (*it_block).erase(it);
            where_is1.erase(a);
    
            if((*it_block).size() == 0){
                auto it_UB_block = UBs.lower_bound({b,it_block});  
                
                if((*it_UB_block).first != B){
                    UBs.erase(it_UB_block);
                    D1.erase(it_block);
                }
            }
        }else{
            auto [it_block,it] = where_is0[a];
            (*it_block).erase(it);
            where_is0.erase(a);
            if((*it_block).size() == 0) D0.erase(it_block); 
        }
    
        actual_value.erase(a);
        size_--;
    }
    
    uniqueDistT selectKth(std::vector<elementT> &v, int k) {
        const auto comparator = [](const auto &a, const auto &b){
            return a.second < b.second;
        };
        miniselect::median_of_ninthers_select(v.begin(), v.begin() + k, v.end(), comparator);
        return v[k].second;
    }

        
    void split(std::list<std::list<elementT>>::iterator it_block){ // O(M) + O(lg(Block Numbers))
        int sz = (*it_block).size();
        
        std::vector<elementT> v((*it_block).begin() , (*it_block).end());
        uniqueDistT med = selectKth(v,(sz/2)); // O(M)
        
        auto pos = it_block;
        pos++;

        auto new_block = D1.insert(pos,std::list<elementT>());
        auto it = (*it_block).begin();
    
        while(it != (*it_block).end()){ // O(M)
            if((*it).second >= med){
                (*new_block).push_back(move(*it));
                auto it_new = (*new_block).end(); it_new--;
                where_is1[(*it).first] = {new_block, it_new};
    
                it = (*it_block).erase(it);
            }else{
                it++;
            }
        }
    

        // Updating UBs   
        // O(lg(Block Numbers))
        uniqueDistT UB1 = {get<0>(med),get<1>(med),get<2>(med),get<3>(med)-1};
        auto it_lb = UBs.lower_bound({UB1,it_min});
        auto [UB2,aux] = (*it_lb);
        
        UBs.insert({UB1,it_block});
        UBs.insert({UB2,new_block});
        
        UBs.erase(it_lb);
    }
    
    void batchPrepend(const std::list<elementT> &l) { // O(|l| log(|l|/M) ) 
        int sz = l.size();
        
        if(sz == 0) return;
        if(sz <= M){
    
            D0.push_front(std::list<elementT>());
            auto new_block = D0.begin();
            
            for(auto &x : l){ 
                auto it = actual_value.find(x.first);
                int exist = (it != actual_value.end()); 
    
                if(exist && it->second > x.second){
                    delete_(x.second);
                }else if(exist){
                    continue;
                }
    
                (*new_block).push_back(x);
                auto it_new = (*new_block).end(); it_new--;
                where_is0[x.first] = {new_block, it_new};
                actual_value[x.first] = x.second;
                size_++;
            }
            if(new_block->size() == 0) D0.erase(new_block);
            return;
        }

        std::vector<elementT> v(l.begin(), l.end());
        uniqueDistT med = selectKth(v, sz/2);
    
        std::list<elementT> less,great;
        for(auto [a,b]: l){
            if(b < med){
                less.push_back({a,b});
            }else if(b > med){
                great.push_back({a,b});
            }
        }
        
        great.push_back({get<2>(med),med});

        batchPrepend(great);
        batchPrepend(less);
    }
};

template<typename wT>
class bmssp { // bmssp class
    int n, k, t, l;

    std::vector<std::vector<std::pair<int, wT>>> ori_adj;
    std::vector<std::vector<std::pair<int, wT>>> adj;
    std::vector<wT> d;
    std::vector<int> pred, path_sz;

    std::vector<int> node_map, node_rev_map;
    
    bool cd_transfomed;

public:
    const wT oo = std::numeric_limits<wT>::max() / 10;
    bmssp(int n_): n(n_) {
        ori_adj.assign(n, {});
    }
    bmssp(const auto &adj) {
        n = adj.size();
        ori_adj = adj;
    }
    
    void addEdge(int a, int b, wT w) {
        ori_adj[a].emplace_back(b, w);
    }

    // if the graph already has constant degree, prepage_graph(false)
    // else, prepage_graph(true)
    void prepare_graph(bool exec_constant_degree_trasnformation = false) {
        cd_transfomed = exec_constant_degree_trasnformation;
        // erase duplicated edges
        std::vector<std::pair<int, int>> tmp_edges(n, {-1, -1});
        for(int i = 0; i < n; i++) {
            std::vector<std::pair<int, wT>> nw_adj;
            nw_adj.reserve(ori_adj[i].size());
            for(auto [j, w]: ori_adj[i]) {
                if(tmp_edges[j].first != i) {
                    nw_adj.emplace_back(j, w);
                    tmp_edges[j] = {i, nw_adj.size() - 1};
                } else {
                    int id = tmp_edges[j].second;
                    nw_adj[id].second = std::min(nw_adj[id].second, w);
                }
            }
            ori_adj[i] = move(nw_adj);
        }
        tmp_edges.clear();

        if(exec_constant_degree_trasnformation == false) {
            adj = move(ori_adj);
            node_map.resize(n);
            node_rev_map.resize(n);
            
            for(int i = 0; i < n; i++) {
                node_map[i] = i;
                node_rev_map[i] = i;
            }

            k = floor(pow(log2(n), 1.0 / 3.0));
            t = floor(pow(log2(n), 2.0 / 3.0));
        } else { // Make the graph become constant degree
            int cnt = 0;
            std::vector<std::map<int, int>> edge_id(n);
            for(int i = 0; i < n; i++) {
                for(auto [j, w]: ori_adj[i]) {
                    if(edge_id[i].find(j) == edge_id[i].end()) {
                        edge_id[i][j] = cnt++;
                        edge_id[j][i] = cnt++;
                    }
                }
            }

            cnt++;
            adj.assign(cnt, {});
            node_map.resize(cnt);
            node_rev_map.resize(cnt);
    
            for(int i = 0; i < n; i++) { // create 0-weight cycles
                for(auto cur = edge_id[i].begin(); cur != edge_id[i].end(); cur++) {
                    auto nxt = next(cur);
                    if(nxt == edge_id[i].end()) nxt = edge_id[i].begin();
                    adj[cur->second].emplace_back(nxt->second, wT());
                    node_rev_map[cur->second] = i;
                }
            }
            for(int i = 0; i < n; i++) { // add edges
                for(auto [j, w]: ori_adj[i]) {
                    adj[edge_id[i][j]].emplace_back(edge_id[j][i], w);
                }
                if(edge_id[i].size()) {
                    node_map[i] = edge_id[i].begin()->second;
                } else {
                    node_map[i] = cnt - 1;
                }
            }
            
            ori_adj.clear();
        }
        
            
        d.resize(adj.size());
        root.resize(adj.size());
        pred.resize(adj.size());
        treesz.resize(adj.size());
        path_sz.resize(adj.size(), 0);
        last_complete_lvl.resize(adj.size());
        pivot_vis.resize(adj.size());
        k = floor(pow(log2(adj.size()), 1.0 / 3.0));
        t = floor(pow(log2(adj.size()), 2.0 / 3.0));
        l = ceil(log2(adj.size()) / t);
        Ds.assign(l, adj.size());
    }

    std::pair<std::vector<wT>, std::vector<int>> execute(int s) {
        fill(d.begin(), d.end(), oo);
        fill(last_complete_lvl.begin(), last_complete_lvl.end(), -1);
        fill(pivot_vis.begin(), pivot_vis.end(), -1);
        for(int i = 0; i < pred.size(); i++) pred[i] = i;
        
        s = toAnyCustomNode(s);
        d[s] = 0;
        path_sz[s] = 0;
        
        const int l = ceil(log2(adj.size()) / t);
        const uniqueDistT inf_dist = {oo, 0, 0, 0};
        bmsspRec(l, inf_dist, {s});
        
        if(!cd_transfomed) {
            return {d, pred};
        } else {
            std::vector<wT> ret_distance(n);
            std::vector<int> ret_pred(n);
            for(int i = 0; i < n; i++) {
                ret_distance[i] = d[toAnyCustomNode(i)];
                ret_pred[i] = customToReal(getPred(toAnyCustomNode(i)));
            }
            return {ret_distance, ret_pred};
        }
    }

    std::vector<int> get_shortest_path(int real_u, const std::vector<int> &real_pred) {
        if(!cd_transfomed) {
            int u = real_u;
            if(d[u] == oo) return {};

            int path_sz = get<1>(getDist(u)) + 1;
            std::vector<int> path(path_sz);
            for(int i = path_sz - 1; i >= 0; i--) {
                path[i] = u;
                u = pred[u];
            }
            return path; // {source, ..., real_u}
        } else {
            int u = real_u;
            if(d[toAnyCustomNode(u)] == oo) return {};

            int max_path_sz = get<1>(getDist(toAnyCustomNode(u))) + 1;
            std::vector<int> path;
            path.reserve(max_path_sz);

            int oldu;
            do {
                path.push_back(u);
                oldu = u;
                u = real_pred[u];
            } while(u != oldu);

            reverse(path.begin(), path.end());
            return path; // {source, ..., real_u}
        }
    }

private:
    inline int toAnyCustomNode(int real_id) {
        return node_map[real_id];
    }
    inline int customToReal(int id) {
        return node_rev_map[id];
    }
    int getPred(int u) {
        int real_u = customToReal(u);

        int dad = u;
        do dad = pred[dad];
        while(customToReal(dad) == real_u && pred[dad] != dad);

        return dad;
    }

    template<typename T>
    bool isUnique(const std::vector<T> &v) {
        auto v2 = v;
        sort(v2.begin(), v2.end());
        v2.erase(unique(v2.begin(), v2.end()), v2.end());
        return v2.size() == v.size();
    }

    // Unique distances helpers: Assumption 2.1
    struct uniqueDistT : std::tuple<wT, int, int, int> {
        static constexpr wT SCALE = 1e10;
        static constexpr wT SCALE_INV = ((wT) 1.0) / SCALE; 

        uniqueDistT() = default;
        static inline wT sanitize(wT w) {
            if constexpr (std::is_floating_point_v<wT>) {
                return std::round(w * SCALE) * SCALE_INV;
            }
            return w;
        }
        uniqueDistT(wT w, int i1, int i2, int i3) 
            : std::tuple<wT, int, int, int>(sanitize(w), i1, i2, i3) {}
    };
    inline uniqueDistT getDist(int u, int v, wT w) {
        return {d[u] + w, path_sz[u] + 1, v, u};
    }
    inline uniqueDistT getDist(int u) {
        return {d[u], path_sz[u], u, pred[u]};
    }
    void updateDist(int u, int v, wT w) {
        pred[v] = u;
        d[v] = d[u] + w;
        path_sz[v] = path_sz[u] + 1;
    }

    // ===================================================================
    std::vector<int> root;
    std::vector<short int> treesz;

    int counter_pivot = 0;
    std::vector<int> pivot_vis;
    std::pair<std::vector<int>, std::vector<int>> findPivots(uniqueDistT B, const std::vector<int> &S) { // Algorithm 1
        counter_pivot++;

        std::vector<int> vis;
        vis.reserve(2 * k * S.size());

        for(int x: S) {
            vis.push_back(x);
            pivot_vis[x] = counter_pivot;
        }

        std::vector<int> active = S;
        for(int x: S) root[x] = x, treesz[x] = 0;
        for(int i = 1; i <= k; i++) {
            std::vector<int> nw_active;
            nw_active.reserve(active.size() * 4);
            for(int u: active) {
                for(auto [v, w]: adj[u]) {
                    if(getDist(u, v, w) <= getDist(v)) {
                        updateDist(u, v, w);
                        if(getDist(v) < B) {
                            root[v] = root[u];
                            nw_active.push_back(v);
                        }
                    }
                }
            }
            for(const auto &x: nw_active) {
                if(pivot_vis[x] != counter_pivot) {
                    pivot_vis[x] = counter_pivot;
                    vis.push_back(x);
                }
            }
            if(vis.size() > k * S.size()) {
                return {S, vis};
            }
            active = move(nw_active);
        }

        std::vector<int> P;
        P.reserve(vis.size() / k);
        for(int u: vis) treesz[root[u]]++;
        for(int u: S) if(treesz[u] >= k) P.push_back(u);
        
        // assert(P.size() <= vis.size() / k);
        return {P, vis};
    }
 
    std::pair<uniqueDistT, std::vector<int>> baseCase(uniqueDistT B, int x) { // Algorithm 2
        std::vector<int> complete;
        complete.reserve(k + 1);
 
        std::priority_queue<uniqueDistT, std::vector<uniqueDistT>, std::greater<uniqueDistT>> heap;
        heap.push(getDist(x));
        while(heap.empty() == false && complete.size() < k + 1) {
            auto du = heap.top();
            int u = get<2>(du);
            heap.pop();

            if(du > getDist(u)) continue;

            complete.push_back(u);
            for(auto [v, w]: adj[u]) {
                auto new_dist = getDist(u, v, w);
                auto old_dist = getDist(v);
                if(new_dist <= old_dist && new_dist < B) {
                    updateDist(u, v, w);
                    heap.push(new_dist);
                }
            }
        }
        if(complete.size() <= k) return {B, complete};
 
        uniqueDistT nB = getDist(complete.back());
        complete.pop_back();

        return {nB, complete};
    }
 
    std::vector<batchPQ<uniqueDistT>> Ds;
    std::vector<short int> last_complete_lvl;
    std::pair<uniqueDistT, std::vector<int>> bmsspRec(short int l, uniqueDistT B, const std::vector<int> &S) { // Algorithm 3
        if(l == 0) return baseCase(B, S[0]);
        
        auto [P, bellman_vis] = findPivots(B, S);
 
        const long long batch_size = (1ll << ((l - 1) * t));
        auto &D = Ds[l - 1];
        D.initialize(batch_size, B);
        for(int p: P) D.insert(getDist(p));
 
        uniqueDistT last_complete_B = B;
        for(int p: P) last_complete_B = std::min(last_complete_B, getDist(p));
 
        std::vector<int> complete;
        const long long quota = k * (1ll << (l * t));
        complete.reserve(quota + bellman_vis.size());
        while(complete.size() < quota && D.size()) {
            auto [trying_B, miniS] = D.pull();
            // all with dist < trying_B, can be reached by miniS <= req 2, alg 3
            auto [complete_B, nw_complete] = bmsspRec(l - 1, trying_B, miniS);
            
            // all new complete_B are greater than the old ones <= point 6, page 10
            // assert(last_complete_B < complete_B);
 
            complete.insert(complete.end(), nw_complete.begin(), nw_complete.end());
            // point 6, page 10 => complete does not intersect with nw_complete
            // assert(isUnique(complete));
 
            std::vector<uniqueDistT> can_prepend;
            can_prepend.reserve(nw_complete.size() * 5 + miniS.size());
            for(int u: nw_complete) {
                D.erase(u); // priority queue fix
                last_complete_lvl[u] = l;
                for(auto [v, w]: adj[u]) {
                    auto new_dist = getDist(u, v, w);
                    if(new_dist <= getDist(v)) {
                        updateDist(u, v, w);
                        if(trying_B <= new_dist && new_dist < B) {
                            D.insert(new_dist); // d[v] can be greater equal than std::min(D), occur 1x per vertex
                        } else if(complete_B <= new_dist && new_dist < trying_B) {
                            can_prepend.emplace_back(new_dist); // d[v] is less than all in D, can occur 1x at each level per vertex
                        }
                    }
                }
            }
            for(int x: miniS) {
                if(complete_B <= getDist(x)) can_prepend.emplace_back(getDist(x));
                // second condition is not necessary
            }
            // can_prepend is not necessarily all unique
            D.batchPrepend(can_prepend);
 
            last_complete_B = complete_B;
        }
        uniqueDistT retB;
        if(D.size() == 0) retB = B;     // successful
        else retB = last_complete_B;    // partial
 
        for(int x: bellman_vis) if(last_complete_lvl[x] != l && getDist(x) < retB) {
            complete.push_back(x); // this get the completed vertices from bellman-ford, it has P in it as well
        }
        // get only the ones not in complete already, for it to become disjoint
        return {retB, complete};
    }
};
}

#endif
// Copyright (c) 2025 Lucas Castro and Thailsson Clementino
// Licensed under the MIT License.

#ifndef CASTRO_THAILSSON_BMSSP_EXPECTED_DUAN25_H
#define CASTRO_THAILSSON_BMSSP_EXPECTED_DUAN25_H

#include<set>
#include<map>
#include<list>
#include<cmath>
#include<vector>
#include<utility>
#include<limits>
#include<queue>
#include<algorithm>
/*          Copyright Danila Kutenin, 2020-.
 * Distributed under the Boost Software License, Version 1.0.
 *    (See accompanying file LICENSE_1_0.txt or copy at
 *          https://boost.org/LICENSE_1_0.txt)
 */
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <functional>
#include <iterator>
#include <type_traits>
#include <utility>

namespace miniselect {
namespace floyd_rivest_detail {

enum floyd_rivest_constants {
  kQCap = 600,
};

template <class Compare>
struct CompareRefType {
  // Pass the comparator by lvalue reference. Or in debug mode, using a
  // debugging wrapper that stores a reference.
  using type = typename std::add_lvalue_reference<Compare>::type;
};

template <class Iter, class Compare,
          class DiffType = typename std::iterator_traits<Iter>::difference_type>
inline void floyd_rivest_select_loop(Iter begin, DiffType left, DiffType right,
                                     DiffType k, Compare comp) {
  while (right > left) {
    DiffType size = right - left;
    if (size > floyd_rivest_constants::kQCap) {
      DiffType n = right - left + 1;
      DiffType i = k - left + 1;

      double z = log(n);
      double s = 0.5 * exp(2 * z / 3);
      double sd = 0.5 * sqrt(z * s * (n - s) / n);
      if (i < n / 2) {
        sd *= -1.0;
      }
      DiffType new_left =
          std::max(left, static_cast<DiffType>(k - i * s / n + sd));
      DiffType new_right =
          std::min(right, static_cast<DiffType>(k + (n - i) * s / n + sd));
      floyd_rivest_select_loop<Iter, Compare, DiffType>(begin, new_left,
                                                        new_right, k, comp);
    }
    DiffType i = left;
    DiffType j = right;

    std::swap(begin[left], begin[k]);
    const bool to_swap = comp(begin[left], begin[right]);
    if (to_swap) {
      std::swap(begin[left], begin[right]);
    }
    // Make sure that non copyable types compile.
    const auto& t = to_swap ? begin[left] : begin[right];
    while (i < j) {
      std::swap(begin[i], begin[j]);
      i++;
      j--;
      while (comp(begin[i], t)) {
        i++;
      }
      while (comp(t, begin[j])) {
        j--;
      }
    }

    if (to_swap) {
      std::swap(begin[left], begin[j]);
    } else {
      j++;
      std::swap(begin[right], begin[j]);
    }

    if (j <= k) {
      left = j + 1;
    }
    if (k <= j) {
      right = j - 1;
    }
  }
}

}  // namespace floyd_rivest_detail

template <class Iter, class Compare>
inline void floyd_rivest_partial_sort(Iter begin, Iter mid, Iter end,
                                      Compare comp) {
  if (begin == end) return;
  if (begin == mid) return;
  using CompType = typename floyd_rivest_detail::CompareRefType<Compare>::type;
  using DiffType = typename std::iterator_traits<Iter>::difference_type;
  floyd_rivest_detail::floyd_rivest_select_loop<Iter, CompType>(
      begin, DiffType{0}, static_cast<DiffType>(end - begin - 1),
      static_cast<DiffType>(mid - begin - 1), comp);
  // std::sort proved to be better than other sorts because of pivoting.
  std::sort<Iter, CompType>(begin, mid, comp);
}

template <class Iter>
inline void floyd_rivest_partial_sort(Iter begin, Iter mid, Iter end) {
  typedef typename std::iterator_traits<Iter>::value_type T;
  floyd_rivest_partial_sort(begin, mid, end, std::less<T>());
}

template <class Iter, class Compare>
inline void floyd_rivest_select(Iter begin, Iter mid, Iter end, Compare comp) {
  if (mid == end) return;
  using CompType = typename floyd_rivest_detail::CompareRefType<Compare>::type;
  using DiffType = typename std::iterator_traits<Iter>::difference_type;
  floyd_rivest_detail::floyd_rivest_select_loop<Iter, CompType>(
      begin, DiffType{0}, static_cast<DiffType>(end - begin - 1),
      static_cast<DiffType>(mid - begin), comp);
}

template <class Iter>
inline void floyd_rivest_select(Iter begin, Iter mid, Iter end) {
  typedef typename std::iterator_traits<Iter>::value_type T;
  floyd_rivest_select(begin, mid, end, std::less<T>());
}

}  // namespace miniselect

///////////////////////// ankerl::unordered_dense::{map, set} /////////////////////////

// A fast & densely stored hashmap and hashset based on robin-hood backward shift deletion.
// Version 4.8.1
// https://github.com/martinus/unordered_dense
//
// Licensed under the MIT License <http://opensource.org/licenses/MIT>.
// SPDX-License-Identifier: MIT
// Copyright (c) 2022 Martin Leitner-Ankerl <martin.ankerl@gmail.com>
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

#ifndef ANKERL_UNORDERED_DENSE_H
#define ANKERL_UNORDERED_DENSE_H

// see https://semver.org/spec/v2.0.0.html
#define ANKERL_UNORDERED_DENSE_VERSION_MAJOR 4 // NOLINT(cppcoreguidelines-macro-usage) incompatible API changes
#define ANKERL_UNORDERED_DENSE_VERSION_MINOR 8 // NOLINT(cppcoreguidelines-macro-usage) backwards compatible functionality
#define ANKERL_UNORDERED_DENSE_VERSION_PATCH 1 // NOLINT(cppcoreguidelines-macro-usage) backwards compatible bug fixes

// API versioning with inline namespace, see https://www.foonathan.net/2018/11/inline-namespaces/

// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define ANKERL_UNORDERED_DENSE_VERSION_CONCAT1(major, minor, patch) v##major##_##minor##_##patch
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define ANKERL_UNORDERED_DENSE_VERSION_CONCAT(major, minor, patch) ANKERL_UNORDERED_DENSE_VERSION_CONCAT1(major, minor, patch)
#define ANKERL_UNORDERED_DENSE_NAMESPACE   \
    ANKERL_UNORDERED_DENSE_VERSION_CONCAT( \
        ANKERL_UNORDERED_DENSE_VERSION_MAJOR, ANKERL_UNORDERED_DENSE_VERSION_MINOR, ANKERL_UNORDERED_DENSE_VERSION_PATCH)

#if defined(_MSVC_LANG)
#    define ANKERL_UNORDERED_DENSE_CPP_VERSION _MSVC_LANG
#else
#    define ANKERL_UNORDERED_DENSE_CPP_VERSION __cplusplus
#endif

#if defined(__GNUC__)
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#    define ANKERL_UNORDERED_DENSE_PACK(decl) decl __attribute__((__packed__))
#elif defined(_MSC_VER)
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#    define ANKERL_UNORDERED_DENSE_PACK(decl) __pragma(pack(push, 1)) decl __pragma(pack(pop))
#endif

// exceptions
#if defined(__cpp_exceptions) || defined(__EXCEPTIONS) || defined(_CPPUNWIND)
#    define ANKERL_UNORDERED_DENSE_HAS_EXCEPTIONS() 1 // NOLINT(cppcoreguidelines-macro-usage)
#else
#    define ANKERL_UNORDERED_DENSE_HAS_EXCEPTIONS() 0 // NOLINT(cppcoreguidelines-macro-usage)
#endif
#ifdef _MSC_VER
#    define ANKERL_UNORDERED_DENSE_NOINLINE __declspec(noinline)
#else
#    define ANKERL_UNORDERED_DENSE_NOINLINE __attribute__((noinline))
#endif

#if defined(__clang__) && defined(__has_attribute)
#    if __has_attribute(__no_sanitize__)
#        define ANKERL_UNORDERED_DENSE_DISABLE_UBSAN_UNSIGNED_INTEGER_CHECK \
            __attribute__((__no_sanitize__("unsigned-integer-overflow")))
#    endif
#endif

#if !defined(ANKERL_UNORDERED_DENSE_DISABLE_UBSAN_UNSIGNED_INTEGER_CHECK)
#    define ANKERL_UNORDERED_DENSE_DISABLE_UBSAN_UNSIGNED_INTEGER_CHECK
#endif

#if ANKERL_UNORDERED_DENSE_CPP_VERSION < 201703L
#    error ankerl::unordered_dense requires C++17 or higher
#else

#    if !defined(ANKERL_UNORDERED_DENSE_STD_MODULE)
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#        define ANKERL_UNORDERED_DENSE_STD_MODULE 0
#    endif

#    if !ANKERL_UNORDERED_DENSE_STD_MODULE
///////////////////////// ankerl::unordered_dense::{map, set} /////////////////////////

// A fast & densely stored hashmap and hashset based on robin-hood backward shift deletion.
// Version 4.8.1
// https://github.com/martinus/unordered_dense
//
// Licensed under the MIT License <http://opensource.org/licenses/MIT>.
// SPDX-License-Identifier: MIT
// Copyright (c) 2022 Martin Leitner-Ankerl <martin.ankerl@gmail.com>
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

#ifndef ANKERL_STL_H
#define ANKERL_STL_H

#include <array>            // for array
#include <cstdint>          // for uint64_t, uint32_t, std::uint8_t, UINT64_C
#include <cstring>          // for size_t, memcpy, memset
#include <functional>       // for equal_to, hash
#include <initializer_list> // for initializer_list
#include <iterator>         // for pair, distance
#include <limits>           // for numeric_limits
#include <memory>           // for allocator, allocator_traits, shared_ptr
#include <optional>         // for optional
#include <stdexcept>        // for out_of_range
#include <string>           // for basic_string
#include <string_view>      // for basic_string_view, hash
#include <tuple>            // for forward_as_tuple
#include <type_traits>      // for enable_if_t, declval, conditional_t, ena...
#include <utility>          // for forward, exchange, pair, as_const, piece...
#include <vector>           // for vector

// <memory_resource> includes <mutex>, which fails to compile if
// targeting GCC >= 13 with the (rewritten) win32 thread model, and
// targeting Windows earlier than Vista (0x600).  GCC predefines
// _REENTRANT when using the 'posix' model, and doesn't when using the
// 'win32' model.
#if defined __MINGW64__ && defined __GNUC__ && __GNUC__ >= 13 && !defined _REENTRANT
// _WIN32_WINNT is guaranteed to be defined here because of the
// <cstdint> inclusion above.
#    ifndef _WIN32_WINNT
#        error "_WIN32_WINNT not defined"
#    endif
#    if _WIN32_WINNT < 0x600
#        define ANKERL_MEMORY_RESOURCE_IS_BAD() 1 // NOLINT(cppcoreguidelines-macro-usage)
#    endif
#endif
#ifndef ANKERL_MEMORY_RESOURCE_IS_BAD
#    define ANKERL_MEMORY_RESOURCE_IS_BAD() 0 // NOLINT(cppcoreguidelines-macro-usage)
#endif

#if defined(__has_include) && !defined(ANKERL_UNORDERED_DENSE_DISABLE_PMR)
#    if __has_include(<memory_resource>) && !ANKERL_MEMORY_RESOURCE_IS_BAD()
#        define ANKERL_UNORDERED_DENSE_PMR std::pmr // NOLINT(cppcoreguidelines-macro-usage)
#        include <memory_resource>                  // for polymorphic_allocator
#    elif __has_include(<experimental/memory_resource>)
#        define ANKERL_UNORDERED_DENSE_PMR std::experimental::pmr // NOLINT(cppcoreguidelines-macro-usage)
#        include <experimental/memory_resource>                   // for polymorphic_allocator
#    endif
#endif

#if defined(_MSC_VER) && defined(_M_X64)
#    include <intrin.h>
#    pragma intrinsic(_umul128)
#endif

#endif

#    endif

#    if __has_cpp_attribute(likely) && __has_cpp_attribute(unlikely) && ANKERL_UNORDERED_DENSE_CPP_VERSION >= 202002L
#        define ANKERL_UNORDERED_DENSE_LIKELY_ATTR [[likely]]     // NOLINT(cppcoreguidelines-macro-usage)
#        define ANKERL_UNORDERED_DENSE_UNLIKELY_ATTR [[unlikely]] // NOLINT(cppcoreguidelines-macro-usage)
#        define ANKERL_UNORDERED_DENSE_LIKELY(x) (x)              // NOLINT(cppcoreguidelines-macro-usage)
#        define ANKERL_UNORDERED_DENSE_UNLIKELY(x) (x)            // NOLINT(cppcoreguidelines-macro-usage)
#    else
#        define ANKERL_UNORDERED_DENSE_LIKELY_ATTR   // NOLINT(cppcoreguidelines-macro-usage)
#        define ANKERL_UNORDERED_DENSE_UNLIKELY_ATTR // NOLINT(cppcoreguidelines-macro-usage)

#        if defined(__GNUC__) || defined(__INTEL_COMPILER) || defined(__clang__)
#            define ANKERL_UNORDERED_DENSE_LIKELY(x) __builtin_expect(x, 1)   // NOLINT(cppcoreguidelines-macro-usage)
#            define ANKERL_UNORDERED_DENSE_UNLIKELY(x) __builtin_expect(x, 0) // NOLINT(cppcoreguidelines-macro-usage)
#        else
#            define ANKERL_UNORDERED_DENSE_LIKELY(x) (x)   // NOLINT(cppcoreguidelines-macro-usage)
#            define ANKERL_UNORDERED_DENSE_UNLIKELY(x) (x) // NOLINT(cppcoreguidelines-macro-usage)
#        endif

#    endif

namespace ankerl::unordered_dense {
inline namespace ANKERL_UNORDERED_DENSE_NAMESPACE {

namespace detail {

#    if ANKERL_UNORDERED_DENSE_HAS_EXCEPTIONS()

// make sure this is not inlined as it is slow and dramatically enlarges code, thus making other
// inlinings more difficult. Throws are also generally the slow path.
[[noreturn]] inline ANKERL_UNORDERED_DENSE_NOINLINE void on_error_key_not_found() {
    throw std::out_of_range("ankerl::unordered_dense::map::at(): key not found");
}
[[noreturn]] inline ANKERL_UNORDERED_DENSE_NOINLINE void on_error_bucket_overflow() {
    throw std::overflow_error("ankerl::unordered_dense: reached max bucket size, cannot increase size");
}
[[noreturn]] inline ANKERL_UNORDERED_DENSE_NOINLINE void on_error_too_many_elements() {
    throw std::out_of_range("ankerl::unordered_dense::map::replace(): too many elements");
}

#    else

[[noreturn]] inline void on_error_key_not_found() {
    abort();
}
[[noreturn]] inline void on_error_bucket_overflow() {
    abort();
}
[[noreturn]] inline void on_error_too_many_elements() {
    abort();
}

#    endif

} // namespace detail

// hash ///////////////////////////////////////////////////////////////////////

// This is a stripped-down implementation of wyhash: https://github.com/wangyi-fudan/wyhash
// No big-endian support (because different values on different machines don't matter),
// hardcodes seed and the secret, reformats the code, and clang-tidy fixes.
namespace detail::wyhash {

inline void mum(std::uint64_t* a, std::uint64_t* b) {
#    if defined(__SIZEOF_INT128__)
    __uint128_t r = *a;
    r *= *b;
    *a = static_cast<std::uint64_t>(r);
    *b = static_cast<std::uint64_t>(r >> 64U);
#    elif defined(_MSC_VER) && defined(_M_X64)
    *a = _umul128(*a, *b, b);
#    else
    std::uint64_t ha = *a >> 32U;
    std::uint64_t hb = *b >> 32U;
    std::uint64_t la = static_cast<std::uint32_t>(*a);
    std::uint64_t lb = static_cast<std::uint32_t>(*b);
    std::uint64_t hi{};
    std::uint64_t lo{};
    std::uint64_t rh = ha * hb;
    std::uint64_t rm0 = ha * lb;
    std::uint64_t rm1 = hb * la;
    std::uint64_t rl = la * lb;
    std::uint64_t t = rl + (rm0 << 32U);
    auto c = static_cast<std::uint64_t>(t < rl);
    lo = t + (rm1 << 32U);
    c += static_cast<std::uint64_t>(lo < t);
    hi = rh + (rm0 >> 32U) + (rm1 >> 32U) + c;
    *a = lo;
    *b = hi;
#    endif
}

// multiply and xor mix function, aka MUM
[[nodiscard]] inline auto mix(std::uint64_t a, std::uint64_t b) -> std::uint64_t {
    mum(&a, &b);
    return a ^ b;
}

// read functions. WARNING: we don't care about endianness, so results are different on big endian!
[[nodiscard]] inline auto r8(const std::uint8_t* p) -> std::uint64_t {
    std::uint64_t v{};
    std::memcpy(&v, p, 8U);
    return v;
}

[[nodiscard]] inline auto r4(const std::uint8_t* p) -> std::uint64_t {
    std::uint32_t v{};
    std::memcpy(&v, p, 4);
    return v;
}

// reads 1, 2, or 3 bytes
[[nodiscard]] inline auto r3(const std::uint8_t* p, std::size_t k) -> std::uint64_t {
    return (static_cast<std::uint64_t>(p[0]) << 16U) | (static_cast<std::uint64_t>(p[k >> 1U]) << 8U) | p[k - 1];
}

[[maybe_unused]] [[nodiscard]] inline auto hash(void const* key, std::size_t len) -> std::uint64_t {
    static constexpr auto secret = std::array{UINT64_C(0xa0761d6478bd642f),
                                              UINT64_C(0xe7037ed1a0b428db),
                                              UINT64_C(0x8ebc6af09c88c6e3),
                                              UINT64_C(0x589965cc75374cc3)};

    auto const* p = static_cast<std::uint8_t const*>(key);
    std::uint64_t seed = secret[0];
    std::uint64_t a{};
    std::uint64_t b{};
    if (ANKERL_UNORDERED_DENSE_LIKELY(len <= 16))
        ANKERL_UNORDERED_DENSE_LIKELY_ATTR {
            if (ANKERL_UNORDERED_DENSE_LIKELY(len >= 4))
                ANKERL_UNORDERED_DENSE_LIKELY_ATTR {
                    a = (r4(p) << 32U) | r4(p + ((len >> 3U) << 2U));
                    b = (r4(p + len - 4) << 32U) | r4(p + len - 4 - ((len >> 3U) << 2U));
                }
            else if (ANKERL_UNORDERED_DENSE_LIKELY(len > 0))
                ANKERL_UNORDERED_DENSE_LIKELY_ATTR {
                    a = r3(p, len);
                    b = 0;
                }
            else {
                a = 0;
                b = 0;
            }
        }
    else {
        std::size_t i = len;
        if (ANKERL_UNORDERED_DENSE_UNLIKELY(i > 48))
            ANKERL_UNORDERED_DENSE_UNLIKELY_ATTR {
                std::uint64_t see1 = seed;
                std::uint64_t see2 = seed;
                do {
                    seed = mix(r8(p) ^ secret[1], r8(p + 8) ^ seed);
                    see1 = mix(r8(p + 16) ^ secret[2], r8(p + 24) ^ see1);
                    see2 = mix(r8(p + 32) ^ secret[3], r8(p + 40) ^ see2);
                    p += 48;
                    i -= 48;
                } while (ANKERL_UNORDERED_DENSE_LIKELY(i > 48));
                seed ^= see1 ^ see2;
            }
        while (ANKERL_UNORDERED_DENSE_UNLIKELY(i > 16))
            ANKERL_UNORDERED_DENSE_UNLIKELY_ATTR {
                seed = mix(r8(p) ^ secret[1], r8(p + 8) ^ seed);
                i -= 16;
                p += 16;
            }
        a = r8(p + i - 16);
        b = r8(p + i - 8);
    }

    return mix(secret[1] ^ len, mix(a ^ secret[1], b ^ seed));
}

[[nodiscard]] inline auto hash(std::uint64_t x) -> std::uint64_t {
    return detail::wyhash::mix(x, UINT64_C(0x9E3779B97F4A7C15));
}

} // namespace detail::wyhash

template <typename T, typename Enable = void>
struct hash {
    auto operator()(T const& obj) const noexcept(noexcept(std::declval<std::hash<T>>().operator()(std::declval<T const&>())))
        -> std::uint64_t {
        return std::hash<T>{}(obj);
    }
};

template <typename T>
struct hash<T, typename std::hash<T>::is_avalanching> {
    using is_avalanching = void;
    auto operator()(T const& obj) const noexcept(noexcept(std::declval<std::hash<T>>().operator()(std::declval<T const&>())))
        -> std::uint64_t {
        return std::hash<T>{}(obj);
    }
};

template <typename CharT>
struct hash<std::basic_string<CharT>> {
    using is_avalanching = void;
    auto operator()(std::basic_string<CharT> const& str) const noexcept -> std::uint64_t {
        return detail::wyhash::hash(str.data(), sizeof(CharT) * str.size());
    }
};

template <typename CharT>
struct hash<std::basic_string_view<CharT>> {
    using is_avalanching = void;
    auto operator()(std::basic_string_view<CharT> const& sv) const noexcept -> std::uint64_t {
        return detail::wyhash::hash(sv.data(), sizeof(CharT) * sv.size());
    }
};

template <class T>
struct hash<T*> {
    using is_avalanching = void;
    auto operator()(T* ptr) const noexcept -> std::uint64_t {
        // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
        return detail::wyhash::hash(reinterpret_cast<std::uintptr_t>(ptr));
    }
};

template <class T>
struct hash<std::unique_ptr<T>> {
    using is_avalanching = void;
    auto operator()(std::unique_ptr<T> const& ptr) const noexcept -> std::uint64_t {
        // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
        return detail::wyhash::hash(reinterpret_cast<std::uintptr_t>(ptr.get()));
    }
};

template <class T>
struct hash<std::shared_ptr<T>> {
    using is_avalanching = void;
    auto operator()(std::shared_ptr<T> const& ptr) const noexcept -> std::uint64_t {
        // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
        return detail::wyhash::hash(reinterpret_cast<std::uintptr_t>(ptr.get()));
    }
};

template <typename Enum>
struct hash<Enum, typename std::enable_if_t<std::is_enum_v<Enum>>> {
    using is_avalanching = void;
    auto operator()(Enum e) const noexcept -> std::uint64_t {
        using underlying = std::underlying_type_t<Enum>;
        return detail::wyhash::hash(static_cast<underlying>(e));
    }
};

template <typename... Args>
struct tuple_hash_helper {
    // Converts the value into 64bit. If it is an integral type, just cast it. Mixing is doing the rest.
    // If it isn't an integral we need to hash it.
    template <typename Arg>
    [[nodiscard]] constexpr static auto to64(Arg const& arg) -> std::uint64_t {
        if constexpr (std::is_integral_v<Arg> || std::is_enum_v<Arg>) {
            return static_cast<std::uint64_t>(arg);
        } else {
            return hash<Arg>{}(arg);
        }
    }

    [[nodiscard]] ANKERL_UNORDERED_DENSE_DISABLE_UBSAN_UNSIGNED_INTEGER_CHECK static auto mix64(std::uint64_t state,
                                                                                                std::uint64_t v)
        -> std::uint64_t {
        return detail::wyhash::mix(state + v, std::uint64_t{0x9ddfea08eb382d69});
    }

    // Creates a buffer that holds all the data from each element of the tuple. If possible we memcpy the data directly. If
    // not, we hash the object and use this for the array. Size of the array is known at compile time, and memcpy is optimized
    // away, so filling the buffer is highly efficient. Finally, call wyhash with this buffer.
    template <typename T, std::size_t... Idx>
    [[nodiscard]] static auto calc_hash(T const& t, std::index_sequence<Idx...> /*unused*/) noexcept -> std::uint64_t {
        auto h = std::uint64_t{};
        ((h = mix64(h, to64(std::get<Idx>(t)))), ...);
        return h;
    }
};

template <typename... Args>
struct hash<std::tuple<Args...>> : tuple_hash_helper<Args...> {
    using is_avalanching = void;
    auto operator()(std::tuple<Args...> const& t) const noexcept -> std::uint64_t {
        return tuple_hash_helper<Args...>::calc_hash(t, std::index_sequence_for<Args...>{});
    }
};

template <typename A, typename B>
struct hash<std::pair<A, B>> : tuple_hash_helper<A, B> {
    using is_avalanching = void;
    auto operator()(std::pair<A, B> const& t) const noexcept -> std::uint64_t {
        return tuple_hash_helper<A, B>::calc_hash(t, std::index_sequence_for<A, B>{});
    }
};

// NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#    define ANKERL_UNORDERED_DENSE_HASH_STATICCAST(T)                         \
        template <>                                                           \
        struct hash<T> {                                                      \
            using is_avalanching = void;                                      \
            auto operator()(T const& obj) const noexcept -> std::uint64_t {   \
                return detail::wyhash::hash(static_cast<std::uint64_t>(obj)); \
            }                                                                 \
        }

#    if defined(__GNUC__) && !defined(__clang__)
#        pragma GCC diagnostic push
#        pragma GCC diagnostic ignored "-Wuseless-cast"
#    endif
// see https://en.cppreference.com/w/cpp/utility/hash
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(bool);
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(char);
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(signed char);
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(unsigned char);
#    if ANKERL_UNORDERED_DENSE_CPP_VERSION >= 202002L && defined(__cpp_char8_t)
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(char8_t);
#    endif
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(char16_t);
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(char32_t);
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(wchar_t);
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(short);
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(unsigned short);
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(int);
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(unsigned int);
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(long);
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(long long);
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(unsigned long);
ANKERL_UNORDERED_DENSE_HASH_STATICCAST(unsigned long long);

#    if defined(__GNUC__) && !defined(__clang__)
#        pragma GCC diagnostic pop
#    endif

// bucket_type //////////////////////////////////////////////////////////

namespace bucket_type {

struct standard {
    static constexpr std::uint32_t dist_inc = 1U << 8U;             // skip 1 byte fingerprint
    static constexpr std::uint32_t fingerprint_mask = dist_inc - 1; // mask for 1 byte of fingerprint

    std::uint32_t m_dist_and_fingerprint; // upper 3 byte: distance to original bucket. lower byte: fingerprint from hash
    std::uint32_t m_value_idx;            // index into the m_values vector.
};

ANKERL_UNORDERED_DENSE_PACK(struct big {
    static constexpr std::uint32_t dist_inc = 1U << 8U;             // skip 1 byte fingerprint
    static constexpr std::uint32_t fingerprint_mask = dist_inc - 1; // mask for 1 byte of fingerprint

    std::uint32_t m_dist_and_fingerprint; // upper 3 byte: distance to original bucket. lower byte: fingerprint from hash
    std::size_t m_value_idx;              // index into the m_values vector.
});

} // namespace bucket_type

namespace detail {

struct nonesuch {};
struct default_container_t {};

template <class Default, class AlwaysVoid, template <class...> class Op, class... Args>
struct detector {
    using value_t = std::false_type;
    using type = Default;
};

template <class Default, template <class...> class Op, class... Args>
struct detector<Default, std::void_t<Op<Args...>>, Op, Args...> {
    using value_t = std::true_type;
    using type = Op<Args...>;
};

template <template <class...> class Op, class... Args>
using is_detected = typename detail::detector<detail::nonesuch, void, Op, Args...>::value_t;

template <template <class...> class Op, class... Args>
constexpr bool is_detected_v = is_detected<Op, Args...>::value;

template <typename T>
using detect_avalanching = typename T::is_avalanching;

template <typename T>
using detect_is_transparent = typename T::is_transparent;

template <typename T>
using detect_iterator = typename T::iterator;

template <typename T>
using detect_reserve = decltype(std::declval<T&>().reserve(std::size_t{}));

// enable_if helpers

template <typename Mapped>
constexpr bool is_map_v = !std::is_void_v<Mapped>;

// clang-format off
template <typename Hash, typename KeyEqual>
constexpr bool is_transparent_v = is_detected_v<detect_is_transparent, Hash> && is_detected_v<detect_is_transparent, KeyEqual>;
// clang-format on

template <typename From, typename To1, typename To2>
constexpr bool is_neither_convertible_v = !std::is_convertible_v<From, To1> && !std::is_convertible_v<From, To2>;

template <typename T>
constexpr bool has_reserve = is_detected_v<detect_reserve, T>;

// base type for map has mapped_type
template <class T>
struct base_table_type_map {
    using mapped_type = T;
};

// base type for set doesn't have mapped_type
struct base_table_type_set {};

} // namespace detail

// Very much like std::deque, but faster for indexing (in most cases). As of now this doesn't implement the full std::vector
// API, but merely what's necessary to work as an underlying container for ankerl::unordered_dense::{map, set}.
// It allocates blocks of equal size and puts them into the m_blocks vector. That means it can grow simply by adding a new
// block to the back of m_blocks, and doesn't double its size like an std::vector. The disadvantage is that memory is not
// linear and thus there is one more indirection necessary for indexing.
template <typename T, typename Allocator = std::allocator<T>, std::size_t MaxSegmentSizeBytes = 4096>
class segmented_vector {
    template <bool IsConst>
    class iter_t;

public:
    using allocator_type = Allocator;
    using pointer = typename std::allocator_traits<allocator_type>::pointer;
    using const_pointer = typename std::allocator_traits<allocator_type>::const_pointer;
    using difference_type = typename std::allocator_traits<allocator_type>::difference_type;
    using value_type = T;
    using size_type = std::size_t;
    using reference = T&;
    using const_reference = T const&;
    using iterator = iter_t<false>;
    using const_iterator = iter_t<true>;

private:
    using vec_alloc = typename std::allocator_traits<Allocator>::template rebind_alloc<pointer>;
    std::vector<pointer, vec_alloc> m_blocks{};
    std::size_t m_size{};

    // Calculates the maximum number for x in  (s << x) <= max_val
    static constexpr auto num_bits_closest(std::size_t max_val, std::size_t s) -> std::size_t {
        auto f = std::size_t{0};
        while (s << (f + 1) <= max_val) {
            ++f;
        }
        return f;
    }

    using self_t = segmented_vector<T, Allocator, MaxSegmentSizeBytes>;
    static constexpr auto num_bits = num_bits_closest(MaxSegmentSizeBytes, sizeof(T));
    static constexpr auto num_elements_in_block = 1U << num_bits;
    static constexpr auto mask = num_elements_in_block - 1U;

    /**
     * Iterator class doubles as const_iterator and iterator
     */
    template <bool IsConst>
    class iter_t {
        using ptr_t = std::conditional_t<IsConst, segmented_vector::const_pointer const*, segmented_vector::pointer*>;
        ptr_t m_data{};
        std::size_t m_idx{};

        template <bool B>
        friend class iter_t;

    public:
        using difference_type = segmented_vector::difference_type;
        using value_type = segmented_vector::value_type;
        using reference = std::conditional_t<IsConst, value_type const&, value_type&>;
        using pointer = std::conditional_t<IsConst, segmented_vector::const_pointer, segmented_vector::pointer>;
        using iterator_category = std::forward_iterator_tag;

        iter_t() noexcept = default;

        template <bool OtherIsConst, typename = std::enable_if_t<IsConst && !OtherIsConst>>
        // NOLINTNEXTLINE(google-explicit-constructor,hicpp-explicit-conversions)
        constexpr iter_t(iter_t<OtherIsConst> const& other) noexcept
            : m_data(other.m_data)
            , m_idx(other.m_idx) {}

        constexpr iter_t(ptr_t data, std::size_t idx) noexcept
            : m_data(data)
            , m_idx(idx) {}

        template <bool OtherIsConst, typename = std::enable_if_t<IsConst && !OtherIsConst>>
        constexpr auto operator=(iter_t<OtherIsConst> const& other) noexcept -> iter_t& {
            m_data = other.m_data;
            m_idx = other.m_idx;
            return *this;
        }

        constexpr auto operator++() noexcept -> iter_t& {
            ++m_idx;
            return *this;
        }

        constexpr auto operator++(int) noexcept -> iter_t {
            iter_t prev(*this);
            this->operator++();
            return prev;
        }

        constexpr auto operator--() noexcept -> iter_t& {
            --m_idx;
            return *this;
        }

        constexpr auto operator--(int) noexcept -> iter_t {
            iter_t prev(*this);
            this->operator--();
            return prev;
        }

        [[nodiscard]] constexpr auto operator+(difference_type diff) const noexcept -> iter_t {
            return {m_data, static_cast<std::size_t>(static_cast<difference_type>(m_idx) + diff)};
        }

        constexpr auto operator+=(difference_type diff) noexcept -> iter_t& {
            m_idx += diff;
            return *this;
        }

        [[nodiscard]] constexpr auto operator-(difference_type diff) const noexcept -> iter_t {
            return {m_data, static_cast<std::size_t>(static_cast<difference_type>(m_idx) - diff)};
        }

        constexpr auto operator-=(difference_type diff) noexcept -> iter_t& {
            m_idx -= diff;
            return *this;
        }

        template <bool OtherIsConst>
        [[nodiscard]] constexpr auto operator-(iter_t<OtherIsConst> const& other) const noexcept -> difference_type {
            return static_cast<difference_type>(m_idx) - static_cast<difference_type>(other.m_idx);
        }

        constexpr auto operator*() const noexcept -> reference {
            return m_data[m_idx >> num_bits][m_idx & mask];
        }

        constexpr auto operator->() const noexcept -> pointer {
            return &m_data[m_idx >> num_bits][m_idx & mask];
        }

        template <bool O>
        [[nodiscard]] constexpr auto operator==(iter_t<O> const& o) const noexcept -> bool {
            return m_idx == o.m_idx;
        }

        template <bool O>
        [[nodiscard]] constexpr auto operator!=(iter_t<O> const& o) const noexcept -> bool {
            return !(*this == o);
        }

        template <bool O>
        [[nodiscard]] constexpr auto operator<(iter_t<O> const& o) const noexcept -> bool {
            return m_idx < o.m_idx;
        }

        template <bool O>
        [[nodiscard]] constexpr auto operator>(iter_t<O> const& o) const noexcept -> bool {
            return o < *this;
        }

        template <bool O>
        [[nodiscard]] constexpr auto operator<=(iter_t<O> const& o) const noexcept -> bool {
            return !(o < *this);
        }

        template <bool O>
        [[nodiscard]] constexpr auto operator>=(iter_t<O> const& o) const noexcept -> bool {
            return !(*this < o);
        }
    };

    // slow path: need to allocate a new segment every once in a while
    void increase_capacity() {
        auto ba = Allocator(m_blocks.get_allocator());
        pointer block = std::allocator_traits<Allocator>::allocate(ba, num_elements_in_block);
        m_blocks.push_back(block);
    }

    // Moves everything from other
    void append_everything_from(segmented_vector&& other) { // NOLINT(cppcoreguidelines-rvalue-reference-param-not-moved)
        reserve(size() + other.size());
        for (auto&& o : other) {
            emplace_back(std::move(o));
        }
    }

    // Copies everything from other
    void append_everything_from(segmented_vector const& other) {
        reserve(size() + other.size());
        for (auto const& o : other) {
            emplace_back(o);
        }
    }

    void dealloc() {
        auto ba = Allocator(m_blocks.get_allocator());
        for (auto ptr : m_blocks) {
            std::allocator_traits<Allocator>::deallocate(ba, ptr, num_elements_in_block);
        }
    }

    [[nodiscard]] static constexpr auto calc_num_blocks_for_capacity(std::size_t capacity) {
        return (capacity + num_elements_in_block - 1U) / num_elements_in_block;
    }

    void resize_shrink(std::size_t new_size) {
        if constexpr (!std::is_trivially_destructible_v<T>) {
            for (std::size_t ix = new_size; ix < m_size; ++ix) {
                operator[](ix).~T();
            }
        }
        m_size = new_size;
    }

public:
    segmented_vector() = default;

    // NOLINTNEXTLINE(google-explicit-constructor,hicpp-explicit-conversions)
    segmented_vector(Allocator alloc)
        : m_blocks(vec_alloc(alloc)) {}

    segmented_vector(segmented_vector&& other, Allocator alloc)
        : segmented_vector(alloc) {
        *this = std::move(other);
    }

    segmented_vector(segmented_vector const& other, Allocator alloc)
        : m_blocks(vec_alloc(alloc)) {
        append_everything_from(other);
    }

    segmented_vector(segmented_vector&& other) noexcept
        : segmented_vector(std::move(other), other.get_allocator()) {}

    segmented_vector(segmented_vector const& other) {
        append_everything_from(other);
    }

    auto operator=(segmented_vector const& other) -> segmented_vector& {
        if (this == &other) {
            return *this;
        }
        clear();
        append_everything_from(other);
        return *this;
    }

    auto operator=(segmented_vector&& other) noexcept -> segmented_vector& {
        clear();
        dealloc();
        if (other.get_allocator() == get_allocator()) {
            m_blocks = std::move(other.m_blocks);
            m_size = std::exchange(other.m_size, {});
        } else {
            // make sure to construct with other's allocator!
            m_blocks = std::vector<pointer, vec_alloc>(vec_alloc(other.get_allocator()));
            append_everything_from(std::move(other));
        }
        return *this;
    }

    ~segmented_vector() {
        clear();
        dealloc();
    }

    [[nodiscard]] constexpr auto size() const -> std::size_t {
        return m_size;
    }

    [[nodiscard]] constexpr auto capacity() const -> std::size_t {
        return m_blocks.size() * num_elements_in_block;
    }

    // Indexing is highly performance critical
    [[nodiscard]] constexpr auto operator[](std::size_t i) const noexcept -> T const& {
        return m_blocks[i >> num_bits][i & mask];
    }

    [[nodiscard]] constexpr auto operator[](std::size_t i) noexcept -> T& {
        return m_blocks[i >> num_bits][i & mask];
    }

    [[nodiscard]] constexpr auto begin() -> iterator {
        return {m_blocks.data(), 0U};
    }
    [[nodiscard]] constexpr auto begin() const -> const_iterator {
        return {m_blocks.data(), 0U};
    }
    [[nodiscard]] constexpr auto cbegin() const -> const_iterator {
        return {m_blocks.data(), 0U};
    }

    [[nodiscard]] constexpr auto end() -> iterator {
        return {m_blocks.data(), m_size};
    }
    [[nodiscard]] constexpr auto end() const -> const_iterator {
        return {m_blocks.data(), m_size};
    }
    [[nodiscard]] constexpr auto cend() const -> const_iterator {
        return {m_blocks.data(), m_size};
    }

    [[nodiscard]] constexpr auto back() -> reference {
        return operator[](m_size - 1);
    }
    [[nodiscard]] constexpr auto back() const -> const_reference {
        return operator[](m_size - 1);
    }

    void pop_back() {
        back().~T();
        --m_size;
    }

    [[nodiscard]] auto empty() const {
        return 0 == m_size;
    }

    void reserve(std::size_t new_capacity) {
        m_blocks.reserve(calc_num_blocks_for_capacity(new_capacity));
        while (new_capacity > capacity()) {
            increase_capacity();
        }
    }

    void resize(std::size_t const count) {
        if (count < m_size) {
            resize_shrink(count);
        } else if (count > m_size) {
            std::size_t const new_elems = count - m_size;
            reserve(count);
            for (std::size_t ix = 0; ix < new_elems; ++ix) {
                emplace_back();
            }
        }
    }

    void resize(std::size_t const count, value_type const& value) {
        if (count < m_size) {
            resize_shrink(count);
        } else if (count > m_size) {
            std::size_t const new_elems = count - m_size;
            reserve(count);
            for (std::size_t ix = 0; ix < new_elems; ++ix) {
                emplace_back(value);
            }
        }
    }

    [[nodiscard]] auto get_allocator() const -> allocator_type {
        return allocator_type{m_blocks.get_allocator()};
    }

    template <class... Args>
    auto emplace_back(Args&&... args) -> reference {
        if (m_size == capacity()) {
            increase_capacity();
        }
        auto* ptr = static_cast<void*>(&operator[](m_size));
        auto& ref = *new (ptr) T(std::forward<Args>(args)...);
        ++m_size;
        return ref;
    }

    void clear() {
        if constexpr (!std::is_trivially_destructible_v<T>) {
            for (std::size_t i = 0, s = size(); i < s; ++i) {
                operator[](i).~T();
            }
        }
        m_size = 0;
    }

    void shrink_to_fit() {
        auto ba = Allocator(m_blocks.get_allocator());
        auto num_blocks_required = calc_num_blocks_for_capacity(m_size);
        while (m_blocks.size() > num_blocks_required) {
            std::allocator_traits<Allocator>::deallocate(ba, m_blocks.back(), num_elements_in_block);
            m_blocks.pop_back();
        }
        m_blocks.shrink_to_fit();
    }
};

namespace detail {

// This is it, the table. Doubles as map and set, and uses `void` for T when its used as a set.
template <class Key,
          class T, // when void, treat it as a set.
          class Hash,
          class KeyEqual,
          class AllocatorOrContainer,
          class Bucket,
          class BucketContainer,
          bool IsSegmented>
class table : public std::conditional_t<is_map_v<T>, base_table_type_map<T>, base_table_type_set> {
    using underlying_value_type = std::conditional_t<is_map_v<T>, std::pair<Key, T>, Key>;
    using underlying_container_type = std::conditional_t<IsSegmented,
                                                         segmented_vector<underlying_value_type, AllocatorOrContainer>,
                                                         std::vector<underlying_value_type, AllocatorOrContainer>>;

public:
    using value_container_type = std::
        conditional_t<is_detected_v<detect_iterator, AllocatorOrContainer>, AllocatorOrContainer, underlying_container_type>;

private:
    using bucket_alloc =
        typename std::allocator_traits<typename value_container_type::allocator_type>::template rebind_alloc<Bucket>;
    using default_bucket_container_type =
        std::conditional_t<IsSegmented, segmented_vector<Bucket, bucket_alloc>, std::vector<Bucket, bucket_alloc>>;

    using bucket_container_type = std::conditional_t<std::is_same_v<BucketContainer, detail::default_container_t>,
                                                     default_bucket_container_type,
                                                     BucketContainer>;

    static constexpr std::uint8_t initial_shifts = 64 - 2; // 2^(64-m_shift) number of buckets
    static constexpr float default_max_load_factor = 0.8F;

public:
    using key_type = Key;
    using value_type = typename value_container_type::value_type;
    using size_type = typename value_container_type::size_type;
    using difference_type = typename value_container_type::difference_type;
    using hasher = Hash;
    using key_equal = KeyEqual;
    using allocator_type = typename value_container_type::allocator_type;
    using reference = typename value_container_type::reference;
    using const_reference = typename value_container_type::const_reference;
    using pointer = typename value_container_type::pointer;
    using const_pointer = typename value_container_type::const_pointer;
    using const_iterator = typename value_container_type::const_iterator;
    using iterator = std::conditional_t<is_map_v<T>, typename value_container_type::iterator, const_iterator>;
    using bucket_type = Bucket;

private:
    using value_idx_type = decltype(Bucket::m_value_idx);
    using dist_and_fingerprint_type = decltype(Bucket::m_dist_and_fingerprint);

    static_assert(std::is_trivially_destructible_v<Bucket>, "assert there's no need to call destructor / std::destroy");
    static_assert(std::is_trivially_copyable_v<Bucket>, "assert we can just memset / memcpy");

    value_container_type m_values{}; // Contains all the key-value pairs in one densely stored container. No holes.
    bucket_container_type m_buckets{};
    std::size_t m_max_bucket_capacity = 0;
    float m_max_load_factor = default_max_load_factor;
    Hash m_hash{};
    KeyEqual m_equal{};
    std::uint8_t m_shifts = initial_shifts;

    [[nodiscard]] auto next(value_idx_type bucket_idx) const -> value_idx_type {
        if (ANKERL_UNORDERED_DENSE_UNLIKELY(bucket_idx + 1U == bucket_count()))
            ANKERL_UNORDERED_DENSE_UNLIKELY_ATTR {
                return 0;
            }

        return static_cast<value_idx_type>(bucket_idx + 1U);
    }

    // Helper to access bucket through pointer types
    [[nodiscard]] static constexpr auto at(bucket_container_type& bucket, std::size_t offset) -> Bucket& {
        return bucket[offset];
    }

    [[nodiscard]] static constexpr auto at(const bucket_container_type& bucket, std::size_t offset) -> const Bucket& {
        return bucket[offset];
    }

    // use the dist_inc and dist_dec functions so that std::uint16_t types work without warning
    [[nodiscard]] static constexpr auto dist_inc(dist_and_fingerprint_type x) -> dist_and_fingerprint_type {
        return static_cast<dist_and_fingerprint_type>(x + Bucket::dist_inc);
    }

    [[nodiscard]] static constexpr auto dist_dec(dist_and_fingerprint_type x) -> dist_and_fingerprint_type {
        return static_cast<dist_and_fingerprint_type>(x - Bucket::dist_inc);
    }

    // The goal of mixed_hash is to always produce a high quality 64bit hash.
    template <typename K>
    [[nodiscard]] constexpr auto mixed_hash(K const& key) const -> std::uint64_t {
        if constexpr (is_detected_v<detect_avalanching, Hash>) {
            // we know that the hash is good because is_avalanching.
            if constexpr (sizeof(decltype(m_hash(key))) < sizeof(std::uint64_t)) {
                // 32bit hash and is_avalanching => multiply with a constant to avalanche bits upwards
                return m_hash(key) * UINT64_C(0x9ddfea08eb382d69);
            } else {
                // 64bit and is_avalanching => only use the hash itself.
                return m_hash(key);
            }
        } else {
            // not is_avalanching => apply wyhash
            return wyhash::hash(m_hash(key));
        }
    }

    [[nodiscard]] constexpr auto dist_and_fingerprint_from_hash(std::uint64_t hash) const -> dist_and_fingerprint_type {
        return Bucket::dist_inc | (static_cast<dist_and_fingerprint_type>(hash) & Bucket::fingerprint_mask);
    }

    [[nodiscard]] constexpr auto bucket_idx_from_hash(std::uint64_t hash) const -> value_idx_type {
        return static_cast<value_idx_type>(hash >> m_shifts);
    }

    [[nodiscard]] static constexpr auto get_key(value_type const& vt) -> key_type const& {
        if constexpr (is_map_v<T>) {
            return vt.first;
        } else {
            return vt;
        }
    }

    template <typename K>
    [[nodiscard]] auto next_while_less(K const& key) const -> Bucket {
        auto hash = mixed_hash(key);
        auto dist_and_fingerprint = dist_and_fingerprint_from_hash(hash);
        auto bucket_idx = bucket_idx_from_hash(hash);

        while (dist_and_fingerprint < at(m_buckets, bucket_idx).m_dist_and_fingerprint) {
            dist_and_fingerprint = dist_inc(dist_and_fingerprint);
            bucket_idx = next(bucket_idx);
        }
        return {dist_and_fingerprint, bucket_idx};
    }

    void place_and_shift_up(Bucket bucket, value_idx_type place) {
        while (0 != at(m_buckets, place).m_dist_and_fingerprint) {
            bucket = std::exchange(at(m_buckets, place), bucket);
            bucket.m_dist_and_fingerprint = dist_inc(bucket.m_dist_and_fingerprint);
            place = next(place);
        }
        at(m_buckets, place) = bucket;
    }

    void erase_and_shift_down(value_idx_type bucket_idx) {
        // shift down until either empty or an element with correct spot is found
        auto next_bucket_idx = next(bucket_idx);
        while (at(m_buckets, next_bucket_idx).m_dist_and_fingerprint >= Bucket::dist_inc * 2) {
            auto& next_bucket = at(m_buckets, next_bucket_idx);
            at(m_buckets, bucket_idx) = {dist_dec(next_bucket.m_dist_and_fingerprint), next_bucket.m_value_idx};
            bucket_idx = std::exchange(next_bucket_idx, next(next_bucket_idx));
        }
        at(m_buckets, bucket_idx) = {};
    }

    [[nodiscard]] static constexpr auto calc_num_buckets(std::uint8_t shifts) -> std::size_t {
        return (std::min)(max_bucket_count(), std::size_t{1} << (64U - shifts));
    }

    [[nodiscard]] constexpr auto calc_shifts_for_size(std::size_t s) const -> std::uint8_t {
        auto shifts = initial_shifts;
        while (shifts > 0 && static_cast<std::size_t>(static_cast<float>(calc_num_buckets(shifts)) * max_load_factor()) < s) {
            --shifts;
        }
        return shifts;
    }

    // assumes m_values has data, m_buckets=m_buckets_end=nullptr, m_shifts is INITIAL_SHIFTS
    void copy_buckets(table const& other) {
        // assumes m_values has already the correct data copied over.
        if (empty()) {
            // when empty, at least allocate an initial buckets and clear them.
            allocate_buckets_from_shift();
            clear_buckets();
        } else {
            m_shifts = other.m_shifts;
            allocate_buckets_from_shift();
            if constexpr (IsSegmented || !std::is_same_v<BucketContainer, default_container_t>) {
                for (auto i = 0UL; i < bucket_count(); ++i) {
                    at(m_buckets, i) = at(other.m_buckets, i);
                }
            } else {
                std::memcpy(m_buckets.data(), other.m_buckets.data(), sizeof(Bucket) * bucket_count());
            }
        }
    }

    /**
     * True when no element can be added any more without increasing the size
     */
    [[nodiscard]] auto is_full() const -> bool {
        return size() > m_max_bucket_capacity;
    }

    void deallocate_buckets() {
        m_buckets.clear();
        m_buckets.shrink_to_fit();
        m_max_bucket_capacity = 0;
    }

    void allocate_buckets_from_shift() {
        auto num_buckets = calc_num_buckets(m_shifts);
        if constexpr (IsSegmented || !std::is_same_v<BucketContainer, default_container_t>) {
            if constexpr (has_reserve<bucket_container_type>) {
                m_buckets.reserve(num_buckets);
            }
            for (std::size_t i = m_buckets.size(); i < num_buckets; ++i) {
                m_buckets.emplace_back();
            }
        } else {
            m_buckets.resize(num_buckets);
        }
        if (num_buckets == max_bucket_count()) {
            // reached the maximum, make sure we can use each bucket
            m_max_bucket_capacity = max_bucket_count();
        } else {
            m_max_bucket_capacity = static_cast<value_idx_type>(static_cast<float>(num_buckets) * max_load_factor());
        }
    }

    void clear_buckets() {
        if constexpr (IsSegmented || !std::is_same_v<BucketContainer, default_container_t>) {
            for (auto&& e : m_buckets) {
                std::memset(&e, 0, sizeof(e));
            }
        } else {
            std::memset(m_buckets.data(), 0, sizeof(Bucket) * bucket_count());
        }
    }

    void clear_and_fill_buckets_from_values() {
        clear_buckets();
        for (value_idx_type value_idx = 0, end_idx = static_cast<value_idx_type>(m_values.size()); value_idx < end_idx;
             ++value_idx) {
            auto const& key = get_key(m_values[value_idx]);
            auto [dist_and_fingerprint, bucket] = next_while_less(key);

            // we know for certain that key has not yet been inserted, so no need to check it.
            place_and_shift_up({dist_and_fingerprint, value_idx}, bucket);
        }
    }

    void increase_size() {
        if (m_max_bucket_capacity == max_bucket_count()) {
            // remove the value again, we can't add it!
            m_values.pop_back();
            on_error_bucket_overflow();
        }
        --m_shifts;
        if constexpr (!IsSegmented || std::is_same_v<BucketContainer, default_container_t>) {
            deallocate_buckets();
        }
        allocate_buckets_from_shift();
        clear_and_fill_buckets_from_values();
    }

    template <typename Op>
    void do_erase(value_idx_type bucket_idx, Op handle_erased_value) {
        auto const value_idx_to_remove = at(m_buckets, bucket_idx).m_value_idx;
        erase_and_shift_down(bucket_idx);
        handle_erased_value(std::move(m_values[value_idx_to_remove]));

        // update m_values
        if (value_idx_to_remove != m_values.size() - 1) {
            // no luck, we'll have to replace the value with the last one and update the index accordingly
            auto& val = m_values[value_idx_to_remove];
            val = std::move(m_values.back());

            // update the values_idx of the moved entry. No need to play the info game, just look until we find the values_idx
            bucket_idx = bucket_idx_from_hash(mixed_hash(get_key(val)));
            auto const values_idx_back = static_cast<value_idx_type>(m_values.size() - 1);
            while (values_idx_back != at(m_buckets, bucket_idx).m_value_idx) {
                bucket_idx = next(bucket_idx);
            }
            at(m_buckets, bucket_idx).m_value_idx = value_idx_to_remove;
        }
        m_values.pop_back();
    }

    template <typename K, typename Op>
    auto do_erase_key(K&& key, Op handle_erased_value) -> std::size_t { // NOLINT(cppcoreguidelines-missing-std-forward)
        if (empty()) {
            return 0;
        }

        auto [dist_and_fingerprint, bucket_idx] = next_while_less(key);

        while (dist_and_fingerprint == at(m_buckets, bucket_idx).m_dist_and_fingerprint &&
               !m_equal(key, get_key(m_values[at(m_buckets, bucket_idx).m_value_idx]))) {
            dist_and_fingerprint = dist_inc(dist_and_fingerprint);
            bucket_idx = next(bucket_idx);
        }

        if (dist_and_fingerprint != at(m_buckets, bucket_idx).m_dist_and_fingerprint) {
            return 0;
        }
        do_erase(bucket_idx, handle_erased_value);
        return 1;
    }

    template <class K, class M>
    auto do_insert_or_assign(K&& key, M&& mapped) -> std::pair<iterator, bool> {
        auto it_isinserted = try_emplace(std::forward<K>(key), std::forward<M>(mapped));
        if (!it_isinserted.second) {
            it_isinserted.first->second = std::forward<M>(mapped);
        }
        return it_isinserted;
    }

    template <typename... Args>
    auto do_place_element(dist_and_fingerprint_type dist_and_fingerprint, value_idx_type bucket_idx, Args&&... args)
        -> std::pair<iterator, bool> {

        // emplace the new value. If that throws an exception, no harm done; index is still in a valid state
        m_values.emplace_back(std::forward<Args>(args)...);

        auto value_idx = static_cast<value_idx_type>(m_values.size() - 1);
        if (ANKERL_UNORDERED_DENSE_UNLIKELY(is_full()))
            ANKERL_UNORDERED_DENSE_UNLIKELY_ATTR {
                increase_size();
            }
        else {
            place_and_shift_up({dist_and_fingerprint, value_idx}, bucket_idx);
        }

        // place element and shift up until we find an empty spot
        return {begin() + static_cast<difference_type>(value_idx), true};
    }

    template <typename K, typename... Args>
    auto do_try_emplace(K&& key, Args&&... args) -> std::pair<iterator, bool> {
        auto hash = mixed_hash(key);
        auto dist_and_fingerprint = dist_and_fingerprint_from_hash(hash);
        auto bucket_idx = bucket_idx_from_hash(hash);

        while (true) {
            auto* bucket = &at(m_buckets, bucket_idx);
            if (dist_and_fingerprint == bucket->m_dist_and_fingerprint) {
                if (m_equal(key, get_key(m_values[bucket->m_value_idx]))) {
                    return {begin() + static_cast<difference_type>(bucket->m_value_idx), false};
                }
            } else if (dist_and_fingerprint > bucket->m_dist_and_fingerprint) {
                return do_place_element(dist_and_fingerprint,
                                        bucket_idx,
                                        std::piecewise_construct,
                                        std::forward_as_tuple(std::forward<K>(key)),
                                        std::forward_as_tuple(std::forward<Args>(args)...));
            }
            dist_and_fingerprint = dist_inc(dist_and_fingerprint);
            bucket_idx = next(bucket_idx);
        }
    }

    template <typename K>
    auto do_find(K const& key) -> iterator {
        if (ANKERL_UNORDERED_DENSE_UNLIKELY(empty()))
            ANKERL_UNORDERED_DENSE_UNLIKELY_ATTR {
                return end();
            }

        auto mh = mixed_hash(key);
        auto dist_and_fingerprint = dist_and_fingerprint_from_hash(mh);
        auto bucket_idx = bucket_idx_from_hash(mh);
        auto* bucket = &at(m_buckets, bucket_idx);

        // unrolled loop. *Always* check a few directly, then enter the loop. This is faster.
        if (dist_and_fingerprint == bucket->m_dist_and_fingerprint && m_equal(key, get_key(m_values[bucket->m_value_idx]))) {
            return begin() + static_cast<difference_type>(bucket->m_value_idx);
        }
        dist_and_fingerprint = dist_inc(dist_and_fingerprint);
        bucket_idx = next(bucket_idx);
        bucket = &at(m_buckets, bucket_idx);

        if (dist_and_fingerprint == bucket->m_dist_and_fingerprint && m_equal(key, get_key(m_values[bucket->m_value_idx]))) {
            return begin() + static_cast<difference_type>(bucket->m_value_idx);
        }
        dist_and_fingerprint = dist_inc(dist_and_fingerprint);
        bucket_idx = next(bucket_idx);
        bucket = &at(m_buckets, bucket_idx);

        while (true) {
            if (dist_and_fingerprint == bucket->m_dist_and_fingerprint) {
                if (m_equal(key, get_key(m_values[bucket->m_value_idx]))) {
                    return begin() + static_cast<difference_type>(bucket->m_value_idx);
                }
            } else if (dist_and_fingerprint > bucket->m_dist_and_fingerprint) {
                return end();
            }
            dist_and_fingerprint = dist_inc(dist_and_fingerprint);
            bucket_idx = next(bucket_idx);
            bucket = &at(m_buckets, bucket_idx);
        }
    }

    template <typename K>
    auto do_find(K const& key) const -> const_iterator {
        return const_cast<table*>(this)->do_find(key); // NOLINT(cppcoreguidelines-pro-type-const-cast)
    }

    template <typename K, typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto do_at(K const& key) -> Q& {
        if (auto it = find(key); ANKERL_UNORDERED_DENSE_LIKELY(end() != it))
            ANKERL_UNORDERED_DENSE_LIKELY_ATTR {
                return it->second;
            }
        on_error_key_not_found();
    }

    template <typename K, typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto do_at(K const& key) const -> Q const& {
        return const_cast<table*>(this)->at(key); // NOLINT(cppcoreguidelines-pro-type-const-cast)
    }

public:
    explicit table(std::size_t bucket_count,
                   Hash const& hash = Hash(),
                   KeyEqual const& equal = KeyEqual(),
                   allocator_type const& alloc_or_container = allocator_type())
        : m_values(alloc_or_container)
        , m_buckets(alloc_or_container)
        , m_hash(hash)
        , m_equal(equal) {
        if (0 != bucket_count) {
            reserve(bucket_count);
        } else {
            allocate_buckets_from_shift();
            clear_buckets();
        }
    }

    table()
        : table(0) {}

    table(std::size_t bucket_count, allocator_type const& alloc)
        : table(bucket_count, Hash(), KeyEqual(), alloc) {}

    table(std::size_t bucket_count, Hash const& hash, allocator_type const& alloc)
        : table(bucket_count, hash, KeyEqual(), alloc) {}

    explicit table(allocator_type const& alloc)
        : table(0, Hash(), KeyEqual(), alloc) {}

    template <class InputIt>
    table(InputIt first,
          InputIt last,
          size_type bucket_count = 0,
          Hash const& hash = Hash(),
          KeyEqual const& equal = KeyEqual(),
          allocator_type const& alloc = allocator_type())
        : table(bucket_count, hash, equal, alloc) {
        insert(first, last);
    }

    template <class InputIt>
    table(InputIt first, InputIt last, size_type bucket_count, allocator_type const& alloc)
        : table(first, last, bucket_count, Hash(), KeyEqual(), alloc) {}

    template <class InputIt>
    table(InputIt first, InputIt last, size_type bucket_count, Hash const& hash, allocator_type const& alloc)
        : table(first, last, bucket_count, hash, KeyEqual(), alloc) {}

    table(table const& other)
        : table(other, other.m_values.get_allocator()) {}

    table(table const& other, allocator_type const& alloc)
        : m_values(other.m_values, alloc)
        , m_max_load_factor(other.m_max_load_factor)
        , m_hash(other.m_hash)
        , m_equal(other.m_equal) {
        copy_buckets(other);
    }

    table(table&& other) noexcept
        : table(std::move(other), other.m_values.get_allocator()) {}

    table(table&& other, allocator_type const& alloc) noexcept
        : m_values(alloc) {
        *this = std::move(other);
    }

    table(std::initializer_list<value_type> ilist,
          std::size_t bucket_count = 0,
          Hash const& hash = Hash(),
          KeyEqual const& equal = KeyEqual(),
          allocator_type const& alloc = allocator_type())
        : table(bucket_count, hash, equal, alloc) {
        insert(ilist);
    }

    table(std::initializer_list<value_type> ilist, size_type bucket_count, allocator_type const& alloc)
        : table(ilist, bucket_count, Hash(), KeyEqual(), alloc) {}

    table(std::initializer_list<value_type> init, size_type bucket_count, Hash const& hash, allocator_type const& alloc)
        : table(init, bucket_count, hash, KeyEqual(), alloc) {}

    ~table() = default;

    auto operator=(table const& other) -> table& {
        if (&other != this) {
            deallocate_buckets(); // deallocate before m_values is set (might have another allocator)
            m_values = other.m_values;
            m_max_load_factor = other.m_max_load_factor;
            m_hash = other.m_hash;
            m_equal = other.m_equal;
            m_shifts = initial_shifts;
            copy_buckets(other);
        }
        return *this;
    }

    auto operator=(table&& other) noexcept(noexcept(std::is_nothrow_move_assignable_v<value_container_type> &&
                                                    std::is_nothrow_move_assignable_v<Hash> &&
                                                    std::is_nothrow_move_assignable_v<KeyEqual>)) -> table& {
        if (&other != this) {
            deallocate_buckets(); // deallocate before m_values is set (might have another allocator)
            m_values = std::move(other.m_values);
            other.m_values.clear();

            // we can only reuse m_buckets when both maps have the same allocator!
            if (get_allocator() == other.get_allocator()) {
                m_buckets = std::move(other.m_buckets);
                other.m_buckets.clear();
                m_max_bucket_capacity = std::exchange(other.m_max_bucket_capacity, 0);
                m_shifts = std::exchange(other.m_shifts, initial_shifts);
                m_max_load_factor = std::exchange(other.m_max_load_factor, default_max_load_factor);
                m_hash = std::exchange(other.m_hash, {});
                m_equal = std::exchange(other.m_equal, {});
                other.allocate_buckets_from_shift();
                other.clear_buckets();
            } else {
                // set max_load_factor *before* copying the other's buckets, so we have the same
                // behavior
                m_max_load_factor = other.m_max_load_factor;

                // copy_buckets sets m_buckets, m_num_buckets, m_max_bucket_capacity, m_shifts
                copy_buckets(other);
                // clear's the other's buckets so other is now already usable.
                other.clear_buckets();
                m_hash = other.m_hash;
                m_equal = other.m_equal;
            }
            // map "other" is now already usable, it's empty.
        }
        return *this;
    }

    auto operator=(std::initializer_list<value_type> ilist) -> table& {
        clear();
        insert(ilist);
        return *this;
    }

    auto get_allocator() const noexcept -> allocator_type {
        return m_values.get_allocator();
    }

    // iterators //////////////////////////////////////////////////////////////

    auto begin() noexcept -> iterator {
        return m_values.begin();
    }

    auto begin() const noexcept -> const_iterator {
        return m_values.begin();
    }

    auto cbegin() const noexcept -> const_iterator {
        return m_values.cbegin();
    }

    auto end() noexcept -> iterator {
        return m_values.end();
    }

    auto cend() const noexcept -> const_iterator {
        return m_values.cend();
    }

    auto end() const noexcept -> const_iterator {
        return m_values.end();
    }

    // capacity ///////////////////////////////////////////////////////////////

    [[nodiscard]] auto empty() const noexcept -> bool {
        return m_values.empty();
    }

    [[nodiscard]] auto size() const noexcept -> std::size_t {
        return m_values.size();
    }

    [[nodiscard]] static constexpr auto max_size() noexcept -> std::size_t {
        if constexpr ((std::numeric_limits<value_idx_type>::max)() == (std::numeric_limits<std::size_t>::max)()) {
            return std::size_t{1} << (sizeof(value_idx_type) * 8 - 1);
        } else {
            return std::size_t{1} << (sizeof(value_idx_type) * 8);
        }
    }

    // modifiers //////////////////////////////////////////////////////////////

    void clear() {
        m_values.clear();
        clear_buckets();
    }

    auto insert(value_type const& value) -> std::pair<iterator, bool> {
        return emplace(value);
    }

    auto insert(value_type&& value) -> std::pair<iterator, bool> {
        return emplace(std::move(value));
    }

    template <class P, std::enable_if_t<std::is_constructible_v<value_type, P&&>, bool> = true>
    auto insert(P&& value) -> std::pair<iterator, bool> {
        return emplace(std::forward<P>(value));
    }

    auto insert(const_iterator /*hint*/, value_type const& value) -> iterator {
        return insert(value).first;
    }

    auto insert(const_iterator /*hint*/, value_type&& value) -> iterator {
        return insert(std::move(value)).first;
    }

    template <class P, std::enable_if_t<std::is_constructible_v<value_type, P&&>, bool> = true>
    auto insert(const_iterator /*hint*/, P&& value) -> iterator {
        return insert(std::forward<P>(value)).first;
    }

    template <class InputIt>
    void insert(InputIt first, InputIt last) {
        while (first != last) {
            insert(*first);
            ++first;
        }
    }

    void insert(std::initializer_list<value_type> ilist) {
        insert(ilist.begin(), ilist.end());
    }

    // nonstandard API: *this is emptied.
    // Also see "A Standard flat_map" https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2022/p0429r9.pdf
    auto extract() && -> value_container_type {
        return std::move(m_values);
    }

    // nonstandard API:
    // Discards the internally held container and replaces it with the one passed. Erases non-unique elements.
    auto replace(value_container_type&& container) {
        if (ANKERL_UNORDERED_DENSE_UNLIKELY(container.size() > max_size()))
            ANKERL_UNORDERED_DENSE_UNLIKELY_ATTR {
                on_error_too_many_elements();
            }
        auto shifts = calc_shifts_for_size(container.size());
        if (0 == bucket_count() || shifts < m_shifts || container.get_allocator() != m_values.get_allocator()) {
            m_shifts = shifts;
            deallocate_buckets();
            allocate_buckets_from_shift();
        }
        clear_buckets();

        m_values = std::move(container);

        // can't use clear_and_fill_buckets_from_values() because container elements might not be unique
        auto value_idx = value_idx_type{};

        // loop until we reach the end of the container. duplicated entries will be replaced with back().
        while (value_idx != static_cast<value_idx_type>(m_values.size())) {
            auto const& key = get_key(m_values[value_idx]);

            auto hash = mixed_hash(key);
            auto dist_and_fingerprint = dist_and_fingerprint_from_hash(hash);
            auto bucket_idx = bucket_idx_from_hash(hash);

            bool key_found = false;
            while (true) {
                auto const& bucket = at(m_buckets, bucket_idx);
                if (dist_and_fingerprint > bucket.m_dist_and_fingerprint) {
                    break;
                }
                if (dist_and_fingerprint == bucket.m_dist_and_fingerprint &&
                    m_equal(key, get_key(m_values[bucket.m_value_idx]))) {
                    key_found = true;
                    break;
                }
                dist_and_fingerprint = dist_inc(dist_and_fingerprint);
                bucket_idx = next(bucket_idx);
            }

            if (key_found) {
                if (value_idx != static_cast<value_idx_type>(m_values.size() - 1)) {
                    m_values[value_idx] = std::move(m_values.back());
                }
                m_values.pop_back();
            } else {
                place_and_shift_up({dist_and_fingerprint, value_idx}, bucket_idx);
                ++value_idx;
            }
        }
    }

    template <class M, typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto insert_or_assign(Key const& key, M&& mapped) -> std::pair<iterator, bool> {
        return do_insert_or_assign(key, std::forward<M>(mapped));
    }

    template <class M, typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto insert_or_assign(Key&& key, M&& mapped) -> std::pair<iterator, bool> {
        return do_insert_or_assign(std::move(key), std::forward<M>(mapped));
    }

    template <typename K,
              typename M,
              typename Q = T,
              typename H = Hash,
              typename KE = KeyEqual,
              std::enable_if_t<is_map_v<Q> && is_transparent_v<H, KE>, bool> = true>
    auto insert_or_assign(K&& key, M&& mapped) -> std::pair<iterator, bool> {
        return do_insert_or_assign(std::forward<K>(key), std::forward<M>(mapped));
    }

    template <class M, typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto insert_or_assign(const_iterator /*hint*/, Key const& key, M&& mapped) -> iterator {
        return do_insert_or_assign(key, std::forward<M>(mapped)).first;
    }

    template <class M, typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto insert_or_assign(const_iterator /*hint*/, Key&& key, M&& mapped) -> iterator {
        return do_insert_or_assign(std::move(key), std::forward<M>(mapped)).first;
    }

    template <typename K,
              typename M,
              typename Q = T,
              typename H = Hash,
              typename KE = KeyEqual,
              std::enable_if_t<is_map_v<Q> && is_transparent_v<H, KE>, bool> = true>
    auto insert_or_assign(const_iterator /*hint*/, K&& key, M&& mapped) -> iterator {
        return do_insert_or_assign(std::forward<K>(key), std::forward<M>(mapped)).first;
    }

    // Single arguments for unordered_set can be used without having to construct the value_type
    template <class K,
              typename Q = T,
              typename H = Hash,
              typename KE = KeyEqual,
              std::enable_if_t<!is_map_v<Q> && is_transparent_v<H, KE>, bool> = true>
    auto emplace(K&& key) -> std::pair<iterator, bool> {
        auto hash = mixed_hash(key);
        auto dist_and_fingerprint = dist_and_fingerprint_from_hash(hash);
        auto bucket_idx = bucket_idx_from_hash(hash);

        while (dist_and_fingerprint <= at(m_buckets, bucket_idx).m_dist_and_fingerprint) {
            if (dist_and_fingerprint == at(m_buckets, bucket_idx).m_dist_and_fingerprint &&
                m_equal(key, m_values[at(m_buckets, bucket_idx).m_value_idx])) {
                // found it, return without ever actually creating anything
                return {begin() + static_cast<difference_type>(at(m_buckets, bucket_idx).m_value_idx), false};
            }
            dist_and_fingerprint = dist_inc(dist_and_fingerprint);
            bucket_idx = next(bucket_idx);
        }

        // value is new, insert element first, so when exception happens we are in a valid state
        return do_place_element(dist_and_fingerprint, bucket_idx, std::forward<K>(key));
    }

    template <class... Args>
    auto emplace(Args&&... args) -> std::pair<iterator, bool> {
        // we have to instantiate the value_type to be able to access the key.
        // 1. emplace_back the object so it is constructed. 2. If the key is already there, pop it later in the loop.
        auto& key = get_key(m_values.emplace_back(std::forward<Args>(args)...));
        auto hash = mixed_hash(key);
        auto dist_and_fingerprint = dist_and_fingerprint_from_hash(hash);
        auto bucket_idx = bucket_idx_from_hash(hash);

        while (dist_and_fingerprint <= at(m_buckets, bucket_idx).m_dist_and_fingerprint) {
            if (dist_and_fingerprint == at(m_buckets, bucket_idx).m_dist_and_fingerprint &&
                m_equal(key, get_key(m_values[at(m_buckets, bucket_idx).m_value_idx]))) {
                m_values.pop_back(); // value was already there, so get rid of it
                return {begin() + static_cast<difference_type>(at(m_buckets, bucket_idx).m_value_idx), false};
            }
            dist_and_fingerprint = dist_inc(dist_and_fingerprint);
            bucket_idx = next(bucket_idx);
        }

        // value is new, place the bucket and shift up until we find an empty spot
        auto value_idx = static_cast<value_idx_type>(m_values.size() - 1);
        if (ANKERL_UNORDERED_DENSE_UNLIKELY(is_full()))
            ANKERL_UNORDERED_DENSE_UNLIKELY_ATTR {
                // increase_size just rehashes all the data we have in m_values
                increase_size();
            }
        else {
            // place element and shift up until we find an empty spot
            place_and_shift_up({dist_and_fingerprint, value_idx}, bucket_idx);
        }
        return {begin() + static_cast<difference_type>(value_idx), true};
    }

    template <class... Args>
    auto emplace_hint(const_iterator /*hint*/, Args&&... args) -> iterator {
        return emplace(std::forward<Args>(args)...).first;
    }

    template <class... Args, typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto try_emplace(Key const& key, Args&&... args) -> std::pair<iterator, bool> {
        return do_try_emplace(key, std::forward<Args>(args)...);
    }

    template <class... Args, typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto try_emplace(Key&& key, Args&&... args) -> std::pair<iterator, bool> {
        return do_try_emplace(std::move(key), std::forward<Args>(args)...);
    }

    template <class... Args, typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto try_emplace(const_iterator /*hint*/, Key const& key, Args&&... args) -> iterator {
        return do_try_emplace(key, std::forward<Args>(args)...).first;
    }

    template <class... Args, typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto try_emplace(const_iterator /*hint*/, Key&& key, Args&&... args) -> iterator {
        return do_try_emplace(std::move(key), std::forward<Args>(args)...).first;
    }

    template <
        typename K,
        typename... Args,
        typename Q = T,
        typename H = Hash,
        typename KE = KeyEqual,
        std::enable_if_t<is_map_v<Q> && is_transparent_v<H, KE> && is_neither_convertible_v<K&&, iterator, const_iterator>,
                         bool> = true>
    auto try_emplace(K&& key, Args&&... args) -> std::pair<iterator, bool> {
        return do_try_emplace(std::forward<K>(key), std::forward<Args>(args)...);
    }

    template <
        typename K,
        typename... Args,
        typename Q = T,
        typename H = Hash,
        typename KE = KeyEqual,
        std::enable_if_t<is_map_v<Q> && is_transparent_v<H, KE> && is_neither_convertible_v<K&&, iterator, const_iterator>,
                         bool> = true>
    auto try_emplace(const_iterator /*hint*/, K&& key, Args&&... args) -> iterator {
        return do_try_emplace(std::forward<K>(key), std::forward<Args>(args)...).first;
    }

    // Replaces the key at the given iterator with new_key. This does not change any other data in the underlying table, so
    // all iterators and references remain valid. However, this operation can fail if new_key already exists in the table.
    // In that case, returns {iterator to the already existing new_key, false} and no change is made.
    //
    // In the case of a set, this effectively removes the old key and inserts the new key at the same spot, which is more
    // efficient than removing the old key and inserting the new key because it avoids repositioning the last element.
    template <typename K>
    auto replace_key(iterator it, K&& new_key) -> std::pair<iterator, bool> {
        auto const new_key_hash = mixed_hash(new_key);

        // first, check if new_key already exists and return if so
        auto dist_and_fingerprint = dist_and_fingerprint_from_hash(new_key_hash);
        auto bucket_idx = bucket_idx_from_hash(new_key_hash);
        while (dist_and_fingerprint <= at(m_buckets, bucket_idx).m_dist_and_fingerprint) {
            auto const& bucket = at(m_buckets, bucket_idx);
            if (dist_and_fingerprint == bucket.m_dist_and_fingerprint &&
                m_equal(new_key, get_key(m_values[bucket.m_value_idx]))) {
                return {begin() + static_cast<difference_type>(bucket.m_value_idx), false};
            }
            dist_and_fingerprint = dist_inc(dist_and_fingerprint);
            bucket_idx = next(bucket_idx);
        }

        // const_cast is needed because iterator for the set is always const, so adding another get_key overload is not
        // feasible.
        auto& target_key = const_cast<key_type&>(get_key(*it));
        auto const old_key_bucket_idx = bucket_idx_from_hash(mixed_hash(target_key));

        // Replace the key before doing any bucket changes. If it throws, no harm done, we are still in a valid state as we
        // have not modified any buckets yet.
        target_key = std::forward<K>(new_key);

        auto const value_idx = static_cast<value_idx_type>(it - begin());

        // Find the bucket containing our value_idx. It's guaranteed we find it, so no other stopping condition needed.
        bucket_idx = old_key_bucket_idx;
        while (value_idx != at(m_buckets, bucket_idx).m_value_idx) {
            bucket_idx = next(bucket_idx);
        }
        erase_and_shift_down(bucket_idx);

        // place the new bucket
        dist_and_fingerprint = dist_and_fingerprint_from_hash(new_key_hash);
        bucket_idx = bucket_idx_from_hash(new_key_hash);
        while (dist_and_fingerprint < at(m_buckets, bucket_idx).m_dist_and_fingerprint) {
            dist_and_fingerprint = dist_inc(dist_and_fingerprint);
            bucket_idx = next(bucket_idx);
        }
        place_and_shift_up({dist_and_fingerprint, value_idx}, bucket_idx);

        return {it, true};
    }

    auto erase(iterator it) -> iterator {
        auto hash = mixed_hash(get_key(*it));
        auto bucket_idx = bucket_idx_from_hash(hash);

        auto const value_idx_to_remove = static_cast<value_idx_type>(it - cbegin());
        while (at(m_buckets, bucket_idx).m_value_idx != value_idx_to_remove) {
            bucket_idx = next(bucket_idx);
        }

        do_erase(bucket_idx, [](value_type const& /*unused*/) -> void {
        });
        return begin() + static_cast<difference_type>(value_idx_to_remove);
    }

    auto extract(iterator it) -> value_type {
        auto hash = mixed_hash(get_key(*it));
        auto bucket_idx = bucket_idx_from_hash(hash);

        auto const value_idx_to_remove = static_cast<value_idx_type>(it - cbegin());
        while (at(m_buckets, bucket_idx).m_value_idx != value_idx_to_remove) {
            bucket_idx = next(bucket_idx);
        }

        auto tmp = std::optional<value_type>{};
        do_erase(bucket_idx, [&tmp](value_type&& val) -> void {
            tmp = std::move(val);
        });
        return std::move(tmp).value();
    }

    template <typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto erase(const_iterator it) -> iterator {
        return erase(begin() + (it - cbegin()));
    }

    template <typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto extract(const_iterator it) -> value_type {
        return extract(begin() + (it - cbegin()));
    }

    auto erase(const_iterator first, const_iterator last) -> iterator {
        auto const idx_first = first - cbegin();
        auto const idx_last = last - cbegin();
        auto const first_to_last = std::distance(first, last);
        auto const last_to_end = std::distance(last, cend());

        // remove elements from left to right which moves elements from the end back
        auto const mid = idx_first + (std::min)(first_to_last, last_to_end);
        auto idx = idx_first;
        while (idx != mid) {
            erase(begin() + idx);
            ++idx;
        }

        // all elements from the right are moved, now remove the last element until all done
        idx = idx_last;
        while (idx != mid) {
            --idx;
            erase(begin() + idx);
        }

        return begin() + idx_first;
    }

    auto erase(Key const& key) -> std::size_t {
        return do_erase_key(key, [](value_type const& /*unused*/) -> void {
        });
    }

    auto extract(Key const& key) -> std::optional<value_type> {
        auto tmp = std::optional<value_type>{};
        do_erase_key(key, [&tmp](value_type&& val) -> void {
            tmp = std::move(val);
        });
        return tmp;
    }

    template <class K, class H = Hash, class KE = KeyEqual, std::enable_if_t<is_transparent_v<H, KE>, bool> = true>
    auto erase(K&& key) -> std::size_t {
        return do_erase_key(std::forward<K>(key), [](value_type const& /*unused*/) -> void {
        });
    }

    template <class K, class H = Hash, class KE = KeyEqual, std::enable_if_t<is_transparent_v<H, KE>, bool> = true>
    auto extract(K&& key) -> std::optional<value_type> {
        auto tmp = std::optional<value_type>{};
        do_erase_key(std::forward<K>(key), [&tmp](value_type&& val) -> void {
            tmp = std::move(val);
        });
        return tmp;
    }

    void swap(table& other) noexcept(noexcept(std::is_nothrow_swappable_v<value_container_type> &&
                                              std::is_nothrow_swappable_v<Hash> && std::is_nothrow_swappable_v<KeyEqual>)) {
        using std::swap;
        swap(other, *this);
    }

    // lookup /////////////////////////////////////////////////////////////////

    template <typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto at(key_type const& key) -> Q& {
        return do_at(key);
    }

    template <typename K,
              typename Q = T,
              typename H = Hash,
              typename KE = KeyEqual,
              std::enable_if_t<is_map_v<Q> && is_transparent_v<H, KE>, bool> = true>
    auto at(K const& key) -> Q& {
        return do_at(key);
    }

    template <typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto at(key_type const& key) const -> Q const& {
        return do_at(key);
    }

    template <typename K,
              typename Q = T,
              typename H = Hash,
              typename KE = KeyEqual,
              std::enable_if_t<is_map_v<Q> && is_transparent_v<H, KE>, bool> = true>
    auto at(K const& key) const -> Q const& {
        return do_at(key);
    }

    template <typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto operator[](Key const& key) -> Q& {
        return try_emplace(key).first->second;
    }

    template <typename Q = T, std::enable_if_t<is_map_v<Q>, bool> = true>
    auto operator[](Key&& key) -> Q& {
        return try_emplace(std::move(key)).first->second;
    }

    template <typename K,
              typename Q = T,
              typename H = Hash,
              typename KE = KeyEqual,
              std::enable_if_t<is_map_v<Q> && is_transparent_v<H, KE>, bool> = true>
    auto operator[](K&& key) -> Q& {
        return try_emplace(std::forward<K>(key)).first->second;
    }

    auto count(Key const& key) const -> std::size_t {
        return find(key) == end() ? 0 : 1;
    }

    template <class K, class H = Hash, class KE = KeyEqual, std::enable_if_t<is_transparent_v<H, KE>, bool> = true>
    auto count(K const& key) const -> std::size_t {
        return find(key) == end() ? 0 : 1;
    }

    auto find(Key const& key) -> iterator {
        return do_find(key);
    }

    auto find(Key const& key) const -> const_iterator {
        return do_find(key);
    }

    template <class K, class H = Hash, class KE = KeyEqual, std::enable_if_t<is_transparent_v<H, KE>, bool> = true>
    auto find(K const& key) -> iterator {
        return do_find(key);
    }

    template <class K, class H = Hash, class KE = KeyEqual, std::enable_if_t<is_transparent_v<H, KE>, bool> = true>
    auto find(K const& key) const -> const_iterator {
        return do_find(key);
    }

    auto contains(Key const& key) const -> bool {
        return find(key) != end();
    }

    template <class K, class H = Hash, class KE = KeyEqual, std::enable_if_t<is_transparent_v<H, KE>, bool> = true>
    auto contains(K const& key) const -> bool {
        return find(key) != end();
    }

    auto equal_range(Key const& key) -> std::pair<iterator, iterator> {
        auto it = do_find(key);
        return {it, it == end() ? end() : it + 1};
    }

    auto equal_range(const Key& key) const -> std::pair<const_iterator, const_iterator> {
        auto it = do_find(key);
        return {it, it == end() ? end() : it + 1};
    }

    template <class K, class H = Hash, class KE = KeyEqual, std::enable_if_t<is_transparent_v<H, KE>, bool> = true>
    auto equal_range(K const& key) -> std::pair<iterator, iterator> {
        auto it = do_find(key);
        return {it, it == end() ? end() : it + 1};
    }

    template <class K, class H = Hash, class KE = KeyEqual, std::enable_if_t<is_transparent_v<H, KE>, bool> = true>
    auto equal_range(K const& key) const -> std::pair<const_iterator, const_iterator> {
        auto it = do_find(key);
        return {it, it == end() ? end() : it + 1};
    }

    // bucket interface ///////////////////////////////////////////////////////

    auto bucket_count() const noexcept -> std::size_t { // NOLINT(modernize-use-nodiscard)
        return m_buckets.size();
    }

    static constexpr auto max_bucket_count() noexcept -> std::size_t { // NOLINT(modernize-use-nodiscard)
        return max_size();
    }

    // hash policy ////////////////////////////////////////////////////////////

    [[nodiscard]] auto load_factor() const -> float {
        return bucket_count() ? static_cast<float>(size()) / static_cast<float>(bucket_count()) : 0.0F;
    }

    [[nodiscard]] auto max_load_factor() const -> float {
        return m_max_load_factor;
    }

    void max_load_factor(float ml) {
        m_max_load_factor = ml;
        if (bucket_count() != max_bucket_count()) {
            m_max_bucket_capacity = static_cast<value_idx_type>(static_cast<float>(bucket_count()) * max_load_factor());
        }
    }

    void rehash(std::size_t count) {
        count = (std::min)(count, max_size());
        auto shifts = calc_shifts_for_size((std::max)(count, size()));
        if (shifts != m_shifts) {
            m_shifts = shifts;
            deallocate_buckets();
            m_values.shrink_to_fit();
            allocate_buckets_from_shift();
            clear_and_fill_buckets_from_values();
        }
    }

    void reserve(std::size_t capa) {
        capa = (std::min)(capa, max_size());
        if constexpr (has_reserve<value_container_type>) {
            // std::deque doesn't have reserve(). Make sure we only call when available
            m_values.reserve(capa);
        }
        auto shifts = calc_shifts_for_size((std::max)(capa, size()));
        if (0 == bucket_count() || shifts < m_shifts) {
            m_shifts = shifts;
            deallocate_buckets();
            allocate_buckets_from_shift();
            clear_and_fill_buckets_from_values();
        }
    }

    // observers //////////////////////////////////////////////////////////////

    auto hash_function() const -> hasher {
        return m_hash;
    }

    auto key_eq() const -> key_equal {
        return m_equal;
    }

    // nonstandard API: expose the underlying values container
    [[nodiscard]] auto values() const noexcept -> value_container_type const& {
        return m_values;
    }

    // non-member functions ///////////////////////////////////////////////////

    friend auto operator==(table const& a, table const& b) -> bool {
        if (&a == &b) {
            return true;
        }
        if (a.size() != b.size()) {
            return false;
        }
        for (auto const& b_entry : b) {
            auto it = a.find(get_key(b_entry));
            if constexpr (is_map_v<T>) {
                // map: check that key is here, then also check that value is the same
                if (a.end() == it || !(b_entry.second == it->second)) {
                    return false;
                }
            } else {
                // set: only check that the key is here
                if (a.end() == it) {
                    return false;
                }
            }
        }
        return true;
    }

    friend auto operator!=(table const& a, table const& b) -> bool {
        return !(a == b);
    }
};

} // namespace detail

template <class Key,
          class T,
          class Hash = hash<Key>,
          class KeyEqual = std::equal_to<Key>,
          class AllocatorOrContainer = std::allocator<std::pair<Key, T>>,
          class Bucket = bucket_type::standard,
          class BucketContainer = detail::default_container_t>
using map = detail::table<Key, T, Hash, KeyEqual, AllocatorOrContainer, Bucket, BucketContainer, false>;

template <class Key,
          class T,
          class Hash = hash<Key>,
          class KeyEqual = std::equal_to<Key>,
          class AllocatorOrContainer = std::allocator<std::pair<Key, T>>,
          class Bucket = bucket_type::standard,
          class BucketContainer = detail::default_container_t>
using segmented_map = detail::table<Key, T, Hash, KeyEqual, AllocatorOrContainer, Bucket, BucketContainer, true>;

template <class Key,
          class Hash = hash<Key>,
          class KeyEqual = std::equal_to<Key>,
          class AllocatorOrContainer = std::allocator<Key>,
          class Bucket = bucket_type::standard,
          class BucketContainer = detail::default_container_t>
using set = detail::table<Key, void, Hash, KeyEqual, AllocatorOrContainer, Bucket, BucketContainer, false>;

template <class Key,
          class Hash = hash<Key>,
          class KeyEqual = std::equal_to<Key>,
          class AllocatorOrContainer = std::allocator<Key>,
          class Bucket = bucket_type::standard,
          class BucketContainer = detail::default_container_t>
using segmented_set = detail::table<Key, void, Hash, KeyEqual, AllocatorOrContainer, Bucket, BucketContainer, true>;

#    if defined(ANKERL_UNORDERED_DENSE_PMR)

namespace pmr {

template <class Key,
          class T,
          class Hash = hash<Key>,
          class KeyEqual = std::equal_to<Key>,
          class Bucket = bucket_type::standard>
using map = detail::table<Key,
                          T,
                          Hash,
                          KeyEqual,
                          ANKERL_UNORDERED_DENSE_PMR::polymorphic_allocator<std::pair<Key, T>>,
                          Bucket,
                          detail::default_container_t,
                          false>;

template <class Key,
          class T,
          class Hash = hash<Key>,
          class KeyEqual = std::equal_to<Key>,
          class Bucket = bucket_type::standard>
using segmented_map = detail::table<Key,
                                    T,
                                    Hash,
                                    KeyEqual,
                                    ANKERL_UNORDERED_DENSE_PMR::polymorphic_allocator<std::pair<Key, T>>,
                                    Bucket,
                                    detail::default_container_t,
                                    true>;

template <class Key, class Hash = hash<Key>, class KeyEqual = std::equal_to<Key>, class Bucket = bucket_type::standard>
using set = detail::table<Key,
                          void,
                          Hash,
                          KeyEqual,
                          ANKERL_UNORDERED_DENSE_PMR::polymorphic_allocator<Key>,
                          Bucket,
                          detail::default_container_t,
                          false>;

template <class Key, class Hash = hash<Key>, class KeyEqual = std::equal_to<Key>, class Bucket = bucket_type::standard>
using segmented_set = detail::table<Key,
                                    void,
                                    Hash,
                                    KeyEqual,
                                    ANKERL_UNORDERED_DENSE_PMR::polymorphic_allocator<Key>,
                                    Bucket,
                                    detail::default_container_t,
                                    true>;

} // namespace pmr

#    endif

// deduction guides ///////////////////////////////////////////////////////////

// deduction guides for alias templates are only possible since C++20
// see https://en.cppreference.com/w/cpp/language/class_template_argument_deduction

} // namespace ANKERL_UNORDERED_DENSE_NAMESPACE
} // namespace ankerl::unordered_dense

// std extensions /////////////////////////////////////////////////////////////

namespace std { // NOLINT(cert-dcl58-cpp)

template <class Key,
          class T,
          class Hash,
          class KeyEqual,
          class AllocatorOrContainer,
          class Bucket,
          class Pred,
          class BucketContainer,
          bool IsSegmented>
// NOLINTNEXTLINE(cert-dcl58-cpp)
auto erase_if(
    ankerl::unordered_dense::detail::table<Key, T, Hash, KeyEqual, AllocatorOrContainer, Bucket, BucketContainer, IsSegmented>&
        map,
    Pred pred) -> std::size_t {
    using map_t = ankerl::unordered_dense::detail::
        table<Key, T, Hash, KeyEqual, AllocatorOrContainer, Bucket, BucketContainer, IsSegmented>;

    // going back to front because erase() invalidates the end iterator
    auto const old_size = map.size();
    auto idx = old_size;
    while (idx) {
        --idx;
        auto it = map.begin() + static_cast<typename map_t::difference_type>(idx);
        if (pred(*it)) {
            map.erase(it);
        }
    }

    return old_size - map.size();
}

} // namespace std

#endif
#endif

namespace spp_expected {

template<typename uniqueDistT>
class batchPQ { // batch priority queue
    template<typename K, typename V>
    using hash_map = ankerl::unordered_dense::map<K, V>;
    using elementT = std::pair<int,uniqueDistT>;
    
    struct CompareUB {
        template <typename It>
        bool operator()(const std::pair<uniqueDistT, It>& a, const std::pair<uniqueDistT, It>& b) const {
            if (a.first != b.first) return a.first < b.first;
            return  addressof(*a.second) < addressof(*b.second);
        }
    };
    
    typename std::list<std::list<elementT>>::iterator it_min;
    
    std::list<std::list<elementT>> D0,D1;
    std::set<std::pair<uniqueDistT,typename std::list<std::list<elementT>>::iterator>,CompareUB> UBs;
    
    int M,size_;
    uniqueDistT B;
    
    hash_map<int, uniqueDistT> actual_value;
    hash_map<int, std::pair<typename std::list<std::list<elementT>>::iterator, typename std::list<elementT>::iterator>> where_is0, where_is1;
    
public:

    batchPQ(int n): actual_value(n), where_is0(n), where_is1(n){} // O(n)

    void initialize(int M_, uniqueDistT B_) { // O(1)
        M = M_; B = B_;
        D0 = {};
        D1 = {std::list<elementT>()};
        UBs = {make_pair(B_,D1.begin())};
        size_ = 0;

        actual_value.clear();
        where_is0.clear(); where_is1.clear();
    }

    int size(){
        return size_;
    }
    
    void insert(uniqueDistT x){ // O(lg(Block Numbers))         
        uniqueDistT b = x;
        int a = get<2>(b);
    
        // checking if exists
        auto it_exist = actual_value.find(a);
        int exist = (it_exist != actual_value.end()); 
    
        if(exist && it_exist->second > b){
            delete_(x);
        }else if(exist){
            return;
        }
        
        // Searching for the first block with UB which is > 
        auto it_UB_block = UBs.lower_bound({b,it_min});
        auto [ub,it_block] = (*it_UB_block);
        
        // Inserting key/value (a,b)
        auto it = it_block->insert(it_block->end(),{a,b});
        where_is1[a] = {it_block, it};
        actual_value[a] = b;
    
        size_++;
    
        // Checking if exceeds the sixe limit M
        if((*it_block).size() > M){
            split(it_block);
        }
    }
    
    void batchPrepend(const std::vector<uniqueDistT> &v){
        std::list<elementT> l;
        for(auto x: v){
            l.push_back({get<2>(x),x});
        }
        batchPrepend(l);
    }

    std::pair<uniqueDistT, std::vector<int>> pull(){ // O(M)
        std::vector<elementT> s0,s1;
        s0.reserve(2 * M); s1.reserve(M);
    
        auto it_block = D0.begin();
        while(it_block != D0.end() && s0.size() <= M){ // O(M)   
            for (const auto& x : *it_block) s0.push_back(x);
            it_block++;
        }
    
        it_block = D1.begin();
        while(it_block != D1.end() && s1.size() <= M){   //O(M)
            for (const auto& x : *it_block) s1.push_back(x);
            it_block++;
        }
    
        if(s1.size() + s0.size() <= M){
            std::vector<int> ret;
            ret.reserve(s1.size()+s0.size());
            for(auto [a,b] : s0) {
                ret.push_back(a);
                delete_({b});
            }
            for(auto [a,b] : s1){
                ret.push_back(a);
                delete_({b});
            } 
            
            return {B, ret};
        }else{  
            std::vector<elementT> &l = s0;
            l.insert(l.end(), s1.begin(), s1.end());

            uniqueDistT med = selectKth(l, M);
            std::vector<int> ret;
            ret.reserve(M);
            for(auto [a,b]: l){
                if(b < med) {
                    ret.push_back(a);
                    delete_({b});
                }
            }
            return {med,ret};
        }
    }
    inline void erase(int key) {
        if(actual_value.find(key) != actual_value.end())
            delete_({-1, -1, key, -1});
    }
    
private:
    void delete_(uniqueDistT x){    
        int a = get<2>(x);
        uniqueDistT b = actual_value[a];
        
        auto it_w = where_is1.find(a);
        if((it_w != where_is1.end())){
            auto [it_block,it] = it_w->second;
            
            (*it_block).erase(it);
            where_is1.erase(a);
    
            if((*it_block).size() == 0){
                auto it_UB_block = UBs.lower_bound({b,it_block});  
                
                if((*it_UB_block).first != B){
                    UBs.erase(it_UB_block);
                    D1.erase(it_block);
                }
            }
        }else{
            auto [it_block,it] = where_is0[a];
            (*it_block).erase(it);
            where_is0.erase(a);
            if((*it_block).size() == 0) D0.erase(it_block); 
        }
    
        actual_value.erase(a);
        size_--;
    }
    
    uniqueDistT selectKth(std::vector<elementT> &v, int k) {
        const auto comparator = [](const auto &a, const auto &b){
            return a.second < b.second;
        };
        miniselect::floyd_rivest_select(v.begin(), v.begin() + k, v.end(), comparator);
        return v[k].second;
    }

        
    void split(std::list<std::list<elementT>>::iterator it_block){ // O(M) + O(lg(Block Numbers))
        int sz = (*it_block).size();
        
        std::vector<elementT> v((*it_block).begin() , (*it_block).end());
        uniqueDistT med = selectKth(v,(sz/2)); // O(M)
        
        auto pos = it_block;
        pos++;

        auto new_block = D1.insert(pos,std::list<elementT>());
        auto it = (*it_block).begin();
    
        while(it != (*it_block).end()){ // O(M)
            if((*it).second >= med){
                (*new_block).push_back(move(*it));
                auto it_new = (*new_block).end(); it_new--;
                where_is1[(*it).first] = {new_block, it_new};
    
                it = (*it_block).erase(it);
            }else{
                it++;
            }
        }
    

        // Updating UBs   
        // O(lg(Block Numbers))
        uniqueDistT UB1 = {get<0>(med),get<1>(med),get<2>(med),get<3>(med)-1};
        auto it_lb = UBs.lower_bound({UB1,it_min});
        auto [UB2,aux] = (*it_lb);
        
        UBs.insert({UB1,it_block});
        UBs.insert({UB2,new_block});
        
        UBs.erase(it_lb);
    }
    
    void batchPrepend(const std::list<elementT> &l) { // O(|l| log(|l|/M) ) 
        int sz = l.size();
        
        if(sz == 0) return;
        if(sz <= M){
    
            D0.push_front(std::list<elementT>());
            auto new_block = D0.begin();
            
            for(auto &x : l){ 
                auto it = actual_value.find(x.first);
                int exist = (it != actual_value.end()); 
    
                if(exist && it->second > x.second){
                    delete_(x.second);
                }else if(exist){
                    continue;
                }
    
                (*new_block).push_back(x);
                auto it_new = (*new_block).end(); it_new--;
                where_is0[x.first] = {new_block, it_new};
                actual_value[x.first] = x.second;
                size_++;
            }
            if(new_block->size() == 0) D0.erase(new_block);
            return;
        }

        std::vector<elementT> v(l.begin(), l.end());
        uniqueDistT med = selectKth(v, sz/2);
    
        std::list<elementT> less,great;
        for(auto [a,b]: l){
            if(b < med){
                less.push_back({a,b});
            }else if(b > med){
                great.push_back({a,b});
            }
        }
        
        great.push_back({get<2>(med),med});

        batchPrepend(great);
        batchPrepend(less);
    }
};

template<typename wT>
class bmssp { // bmssp class
    int n, k, t, l;

    std::vector<std::vector<std::pair<int, wT>>> ori_adj;
    std::vector<std::vector<std::pair<int, wT>>> adj;
    std::vector<wT> d;
    std::vector<int> pred, path_sz;

    std::vector<int> node_map, node_rev_map;
    
    bool cd_transfomed;

public:
    const wT oo = std::numeric_limits<wT>::max() / 10;
    bmssp(int n_): n(n_) {
        ori_adj.assign(n, {});
    }
    bmssp(const auto &adj) {
        n = adj.size();
        ori_adj = adj;
    }
    
    void addEdge(int a, int b, wT w) {
        ori_adj[a].emplace_back(b, w);
    }

    // if the graph already has constant degree, prepage_graph(false)
    // else, prepage_graph(true)
    void prepare_graph(bool exec_constant_degree_trasnformation = false) {
        cd_transfomed = exec_constant_degree_trasnformation;
        // erase duplicated edges
        std::vector<std::pair<int, int>> tmp_edges(n, {-1, -1});
        for(int i = 0; i < n; i++) {
            std::vector<std::pair<int, wT>> nw_adj;
            nw_adj.reserve(ori_adj[i].size());
            for(auto [j, w]: ori_adj[i]) {
                if(tmp_edges[j].first != i) {
                    nw_adj.emplace_back(j, w);
                    tmp_edges[j] = {i, nw_adj.size() - 1};
                } else {
                    int id = tmp_edges[j].second;
                    nw_adj[id].second = std::min(nw_adj[id].second, w);
                }
            }
            ori_adj[i] = move(nw_adj);
        }
        tmp_edges.clear();

        if(exec_constant_degree_trasnformation == false) {
            adj = move(ori_adj);
            node_map.resize(n);
            node_rev_map.resize(n);
            
            for(int i = 0; i < n; i++) {
                node_map[i] = i;
                node_rev_map[i] = i;
            }

            k = floor(pow(log2(n), 1.0 / 3.0));
            t = floor(pow(log2(n), 2.0 / 3.0));
        } else { // Make the graph become constant degree
            int cnt = 0;
            std::vector<std::map<int, int>> edge_id(n);
            for(int i = 0; i < n; i++) {
                for(auto [j, w]: ori_adj[i]) {
                    if(edge_id[i].find(j) == edge_id[i].end()) {
                        edge_id[i][j] = cnt++;
                        edge_id[j][i] = cnt++;
                    }
                }
            }

            cnt++;
            adj.assign(cnt, {});
            node_map.resize(cnt);
            node_rev_map.resize(cnt);
    
            for(int i = 0; i < n; i++) { // create 0-weight cycles
                for(auto cur = edge_id[i].begin(); cur != edge_id[i].end(); cur++) {
                    auto nxt = next(cur);
                    if(nxt == edge_id[i].end()) nxt = edge_id[i].begin();
                    adj[cur->second].emplace_back(nxt->second, wT());
                    node_rev_map[cur->second] = i;
                }
            }
            for(int i = 0; i < n; i++) { // add edges
                for(auto [j, w]: ori_adj[i]) {
                    adj[edge_id[i][j]].emplace_back(edge_id[j][i], w);
                }
                if(edge_id[i].size()) {
                    node_map[i] = edge_id[i].begin()->second;
                } else {
                    node_map[i] = cnt - 1;
                }
            }
            
            ori_adj.clear();
        }
        
            
        d.resize(adj.size());
        root.resize(adj.size());
        pred.resize(adj.size());
        treesz.resize(adj.size());
        path_sz.resize(adj.size(), 0);
        last_complete_lvl.resize(adj.size());
        pivot_vis.resize(adj.size());
        k = floor(pow(log2(adj.size()), 1.0 / 3.0));
        t = floor(pow(log2(adj.size()), 2.0 / 3.0));
        l = ceil(log2(adj.size()) / t);
        Ds.assign(l, adj.size());
    }

    std::pair<std::vector<wT>, std::vector<int>> execute(int s) {
        fill(d.begin(), d.end(), oo);
        fill(last_complete_lvl.begin(), last_complete_lvl.end(), -1);
        fill(pivot_vis.begin(), pivot_vis.end(), -1);
        for(int i = 0; i < pred.size(); i++) pred[i] = i;
        
        s = toAnyCustomNode(s);
        d[s] = 0;
        path_sz[s] = 0;
        
        const int l = ceil(log2(adj.size()) / t);
        const uniqueDistT inf_dist = {oo, 0, 0, 0};
        bmsspRec(l, inf_dist, {s});
        
        if(!cd_transfomed) {
            return {d, pred};
        } else {
            std::vector<wT> ret_distance(n);
            std::vector<int> ret_pred(n);
            for(int i = 0; i < n; i++) {
                ret_distance[i] = d[toAnyCustomNode(i)];
                ret_pred[i] = customToReal(getPred(toAnyCustomNode(i)));
            }
            return {ret_distance, ret_pred};
        }
    }

    std::vector<int> get_shortest_path(int real_u, const std::vector<int> &real_pred) {
        if(!cd_transfomed) {
            int u = real_u;
            if(d[u] == oo) return {};

            int path_sz = get<1>(getDist(u)) + 1;
            std::vector<int> path(path_sz);
            for(int i = path_sz - 1; i >= 0; i--) {
                path[i] = u;
                u = pred[u];
            }
            return path; // {source, ..., real_u}
        } else {
            int u = real_u;
            if(d[toAnyCustomNode(u)] == oo) return {};

            int max_path_sz = get<1>(getDist(toAnyCustomNode(u))) + 1;
            std::vector<int> path;
            path.reserve(max_path_sz);

            int oldu;
            do {
                path.push_back(u);
                oldu = u;
                u = real_pred[u];
            } while(u != oldu);

            reverse(path.begin(), path.end());
            return path; // {source, ..., real_u}
        }
    }
private:
    inline int toAnyCustomNode(int real_id) {
        return node_map[real_id];
    }
    inline int customToReal(int id) {
        return node_rev_map[id];
    }
    int getPred(int u) {
        int real_u = customToReal(u);

        int dad = u;
        do dad = pred[dad];
        while(customToReal(dad) == real_u && pred[dad] != dad);

        return dad;
    }

    template<typename T>
    bool isUnique(const std::vector<T> &v) {
        auto v2 = v;
        sort(v2.begin(), v2.end());
        v2.erase(unique(v2.begin(), v2.end()), v2.end());
        return v2.size() == v.size();
    }

    // Unique distances helpers: Assumption 2.1
    struct uniqueDistT : std::tuple<wT, int, int, int> {
        static constexpr wT SCALE = 1e10;
        static constexpr wT SCALE_INV = ((wT) 1.0) / SCALE; 

        uniqueDistT() = default;
        static inline wT sanitize(wT w) {
            if constexpr (std::is_floating_point_v<wT>) {
                return std::round(w * SCALE) * SCALE_INV;
            }
            return w;
        }
        uniqueDistT(wT w, int i1, int i2, int i3) 
            : std::tuple<wT, int, int, int>(sanitize(w), i1, i2, i3) {}
    };
    inline uniqueDistT getDist(int u, int v, wT w) {
        return {d[u] + w, path_sz[u] + 1, v, u};
    }
    inline uniqueDistT getDist(int u) {
        return {d[u], path_sz[u], u, pred[u]};
    }
    void updateDist(int u, int v, wT w) {
        pred[v] = u;
        d[v] = d[u] + w;
        path_sz[v] = path_sz[u] + 1;
    }

    // ===================================================================
    std::vector<int> root;
    std::vector<short int> treesz;

    int counter_pivot = 0;
    std::vector<int> pivot_vis;
    std::pair<std::vector<int>, std::vector<int>> findPivots(uniqueDistT B, const std::vector<int> &S) { // Algorithm 1
        counter_pivot++;

        std::vector<int> vis;
        vis.reserve(2 * k * S.size());

        for(int x: S) {
            vis.push_back(x);
            pivot_vis[x] = counter_pivot;
        }

        std::vector<int> active = S;
        for(int x: S) root[x] = x, treesz[x] = 0;
        for(int i = 1; i <= k; i++) {
            std::vector<int> nw_active;
            nw_active.reserve(active.size() * 4);
            for(int u: active) {
                for(auto [v, w]: adj[u]) {
                    if(getDist(u, v, w) <= getDist(v)) {
                        updateDist(u, v, w);
                        if(getDist(v) < B) {
                            root[v] = root[u];
                            nw_active.push_back(v);
                        }
                    }
                }
            }
            for(const auto &x: nw_active) {
                if(pivot_vis[x] != counter_pivot) {
                    pivot_vis[x] = counter_pivot;
                    vis.push_back(x);
                }
            }
            if(vis.size() > k * S.size()) {
                return {S, vis};
            }
            active = move(nw_active);
        }

        std::vector<int> P;
        P.reserve(vis.size() / k);
        for(int u: vis) treesz[root[u]]++;
        for(int u: S) if(treesz[u] >= k) P.push_back(u);
        
        // assert(P.size() <= vis.size() / k);
        return {P, vis};
    }
 
    std::pair<uniqueDistT, std::vector<int>> baseCase(uniqueDistT B, int x) { // Algorithm 2
        std::vector<int> complete;
        complete.reserve(k + 1);
 
        std::priority_queue<uniqueDistT, std::vector<uniqueDistT>, std::greater<uniqueDistT>> heap;
        heap.push(getDist(x));
        while(heap.empty() == false && complete.size() < k + 1) {
            auto du = heap.top();
            int u = get<2>(du);
            heap.pop();

            if(du > getDist(u)) continue;

            complete.push_back(u);
            for(auto [v, w]: adj[u]) {
                auto new_dist = getDist(u, v, w);
                auto old_dist = getDist(v);
                if(new_dist <= old_dist && new_dist < B) {
                    updateDist(u, v, w);
                    heap.push(new_dist);
                }
            }
        }
        if(complete.size() <= k) return {B, complete};
 
        uniqueDistT nB = getDist(complete.back());
        complete.pop_back();

        return {nB, complete};
    }
 
    std::vector<batchPQ<uniqueDistT>> Ds;
    std::vector<short int> last_complete_lvl;
    std::pair<uniqueDistT, std::vector<int>> bmsspRec(short int l, uniqueDistT B, const std::vector<int> &S) { // Algorithm 3
        if(l == 0) return baseCase(B, S[0]);
        
        auto [P, bellman_vis] = findPivots(B, S);
 
        const long long batch_size = (1ll << ((l - 1) * t));
        auto &D = Ds[l - 1];
        D.initialize(batch_size, B);
        for(int p: P) D.insert(getDist(p));
 
        uniqueDistT last_complete_B = B;
        for(int p: P) last_complete_B = std::min(last_complete_B, getDist(p));
 
        std::vector<int> complete;
        const long long quota = k * (1ll << (l * t));
        complete.reserve(quota + bellman_vis.size());
        while(complete.size() < quota && D.size()) {
            auto [trying_B, miniS] = D.pull();
            // all with dist < trying_B, can be reached by miniS <= req 2, alg 3
            auto [complete_B, nw_complete] = bmsspRec(l - 1, trying_B, miniS);
            
            // all new complete_B are greater than the old ones <= point 6, page 10
            // assert(last_complete_B < complete_B);
 
            complete.insert(complete.end(), nw_complete.begin(), nw_complete.end());
            // point 6, page 10 => complete does not intersect with nw_complete
            // assert(isUnique(complete));
 
            std::vector<uniqueDistT> can_prepend;
            can_prepend.reserve(nw_complete.size() * 5 + miniS.size());
            for(int u: nw_complete) {
                D.erase(u); // priority queue fix
                last_complete_lvl[u] = l;
                for(auto [v, w]: adj[u]) {
                    auto new_dist = getDist(u, v, w);
                    if(new_dist <= getDist(v)) {
                        updateDist(u, v, w);
                        if(trying_B <= new_dist && new_dist < B) {
                            D.insert(new_dist); // d[v] can be greater equal than std::min(D), occur 1x per vertex
                        } else if(complete_B <= new_dist && new_dist < trying_B) {
                            can_prepend.emplace_back(new_dist); // d[v] is less than all in D, can occur 1x at each level per vertex
                        }
                    }
                }
            }
            for(int x: miniS) {
                if(complete_B <= getDist(x)) can_prepend.emplace_back(getDist(x));
                // second condition is not necessary
            }
            // can_prepend is not necessarily all unique
            D.batchPrepend(can_prepend);
 
            last_complete_B = complete_B;
        }
        uniqueDistT retB;
        if(D.size() == 0) retB = B;     // successful
        else retB = last_complete_B;    // partial
 
        for(int x: bellman_vis) if(last_complete_lvl[x] != l && getDist(x) < retB) {
            complete.push_back(x); // this get the completed vertices from bellman-ford, it has P in it as well
        }
        // get only the ones not in complete already, for it to become disjoint
        return {retB, complete};
    }
};
}

#endif