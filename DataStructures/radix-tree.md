Data Structures in the Linux Kernel
================================================================================

Radix tree
--------------------------------------------------------------------------------

As you already know linux kernel provides many different libraries and functions which implement different data structures and algorithms. In this part we will consider one of these data structures - [Radix tree](http://en.wikipedia.org/wiki/Radix_tree). There are two files which are related to `radix tree` implementation and API in the linux kernel:

* [include/linux/radix-tree.h](https://github.com/torvalds/linux/blob/master/include/linux/radix-tree.h)
* [lib/radix-tree.c](https://github.com/torvalds/linux/blob/master/lib/radix-tree.c)

Lets talk about what is `radix tree`. Radix tree is a `compressed trie` where [trie](http://en.wikipedia.org/wiki/Trie) is a data structure which implements interface of an associative array and allows to store values as `key-value`. The keys are usually strings, but any other data type can be used as well. Trie is different from any `n-tree` in its nodes. Nodes of a trie do not store keys, instead, a node of a trie stores single character labels. The key which is related to a given node is derived by traversing from the root of the tree to this node. For example:


```
               +-----------+
               |           |
               |    " "    |
               |           |
        +------+-----------+------+
        |                         |
        |                         |
   +----v------+            +-----v-----+
   |           |            |           |
   |    g      |            |     c     |
   |           |            |           |
   +-----------+            +-----------+
        |                         |
        |                         |
   +----v------+            +-----v-----+
   |           |            |           |
   |    o      |            |     a     |
   |           |            |           |
   +-----------+            +-----------+
                                  |
                                  |
                            +-----v-----+
                            |           |
                            |     t     |
                            |           |
                            +-----------+
```

So in this example, we can see the `trie` with keys, `go` and `cat`. The compressed trie or `radix tree` differs from `trie`, such that all intermediates nodes which have only one child are removed.

Radix tree in linux kernel is the datastructure which maps values to the integer key. It is represented by the following structures from the file [include/linux/radix-tree.h](https://github.com/torvalds/linux/blob/master/include/linux/radix-tree.h):

```C
struct radix_tree_root {
         unsigned int            height;
         gfp_t                   gfp_mask;
         struct radix_tree_node  __rcu *rnode;
};
```

This structure presents the root of a radix tree and contains three fields:

* `height`   - height of the tree;
* `gfp_mask` - tells how memory allocations are to be performed;
* `rnode`    - pointer to the child node.

The first structure we will discuss is `gfp_mask`:

Low-level kernel memory allocation functions take a set of flags as - `gfp_mask`, which describes how that allocation is to be performed. These `GFP_` flags which control the allocation process can have following values, (`GF_NOIO` flag) be sleep and wait for memory, (`__GFP_HIGHMEM` flag) is high memory can be used, (`GFP_ATOMIC` flag) is allocation process high-priority and can't sleep etc.

The next structure is `rnode`:

```C
struct radix_tree_node {
        unsigned int    path;
        unsigned int    count;
        union {
                struct {
                        struct radix_tree_node *parent;
                        void *private_data;
                };
                struct rcu_head rcu_head;
        };
        /* For tree user */
        struct list_head private_list;
        void __rcu      *slots[RADIX_TREE_MAP_SIZE];
        unsigned long   tags[RADIX_TREE_MAX_TAGS][RADIX_TREE_TAG_LONGS];
};
```

This structure contains information about the offset in a parent and height from the bottom, count of the child nodes and fields for accessing and freeing a node. The fields are described below:

* `path` - offset in parent & height from the bottom;
* `count` - count of the child nodes;
* `parent` - pointer to the parent node;
* `private_data` - used by the user of a tree;
* `rcu_head` - used for freeing a node;
* `private_list` - used by the user of a tree;

The two last fields of the `radix_tree_node` - `tags` and `slots` are important and interesting. Every node can contains a set of slots which are store pointers to the data. Empty slots in the linux kernel radix tree implementation store `NULL`. Radix tree in the linux kernel also supports tags which are associated with the `tags` fields in the `radix_tree_node` structure. Tags allow to set individual bits on records which are stored in the radix tree.

Now we know about radix tree structure, time to look on its API.

Linux kernel radix tree API
---------------------------------------------------------------------------------

We start from the datastructure intialization. There are two ways to initialize new radix tree. The first is to use `RADIX_TREE` macro:

```C
RADIX_TREE(name, gfp_mask);
````

As you can see we pass the `name` parameter, so with the `RADIX_TREE` macro we can define and initialize radix tree with the given name. Implementation of the `RADIX_TREE` is easy:

```C
#define RADIX_TREE(name, mask) \
         struct radix_tree_root name = RADIX_TREE_INIT(mask)

#define RADIX_TREE_INIT(mask)   { \
        .height = 0,              \
        .gfp_mask = (mask),       \
        .rnode = NULL,            \
}
```

At the beginning of the `RADIX_TREE` macro we define instance of the `radix_tree_root` structure with the given name and call `RADIX_TREE_INIT` macro with the given mask. The `RADIX_TREE_INIT` macro just initializes `radix_tree_root` structure with the default values and the given mask.

The second way is to define `radix_tree_root` structure by hand and pass it with mask to the `INIT_RADIX_TREE` macro:

```C
struct radix_tree_root my_radix_tree;
INIT_RADIX_TREE(my_tree, gfp_mask_for_my_radix_tree);
```

where:

```C
#define INIT_RADIX_TREE(root, mask)  \
do {                                 \
        (root)->height = 0;          \
        (root)->gfp_mask = (mask);   \
        (root)->rnode = NULL;        \
} while (0)
```

makes the same initialziation with default values as it does `RADIX_TREE_INIT` macro.

The next are two functions for the inserting and deleting records to/from a radix tree:

* `radix_tree_insert`;
* `radix_tree_delete`.

The first `radix_tree_insert` function takes three parameters:

* root of a radix tree;
* index key;
* data to insert;

The `radix_tree_delete` function takes the same set of parameters as the `radix_tree_insert`, but without data.

The search in a radix tree implemented in two ways:

* `radix_tree_lookup`;
* `radix_tree_gang_lookup`;
* `radix_tree_lookup_slot`.

The first `radix_tree_lookup` function takes two parameters:

* root of a radix tree;
* index key;

This function tries to find the given key in the tree and returns associated record with this key. The second `radix_tree_gang_lookup` function have the following signature

```C
unsigned int radix_tree_gang_lookup(struct radix_tree_root *root,
                                    void **results,
                                    unsigned long first_index,
                                    unsigned int max_items);
```

and returns number of records, sorted by the keys, starting from the first index. Number of the returned records will be not greater than `max_items` value.

And the last `radix_tree_lookup_slot` function will return the slot which will contain the data.

Links
---------------------------------------------------------------------------------

* [Radix tree](http://en.wikipedia.org/wiki/Radix_tree)
* [Trie](http://en.wikipedia.org/wiki/Trie)
