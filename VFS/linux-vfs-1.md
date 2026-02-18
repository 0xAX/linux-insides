# Virtual File System in Linux. Part 1.

## Introduction

The Linux kernel supports a lot of different file systems, from the standard ext4 to network file systems like NFS, and pseudo-filesystems like procfs. There are many types of file system formats, but when users use the system, they can perform consistent operations such as opening, reading, and writing on all files. Various file operations are performed through a unified system call interface (such as open, read, write, close), and various file systems can be mounted through mount. So behind this, there must be a unified abstraction layer responsible for hiding the differences between file systems for users and exposing unified interfaces for upper-layer use. This is where VFS comes into play.

In this part, we will explore the core concepts and data structures that make this abstraction possible.

## Data structures in VFS

Since VFS acts as an abstraction layer, its data structure design must have abstraction capabilities. Since the Linux kernel is written in C, unlike OOP languages ​​that can easily implement polymorphism through class, C language implements polymorphism in a special way, which needs to be implemented through function pointers. Now, we will introduce several core data structures of VFS and the entities they abstractly represent.

The VFS is built around four primary object types: the **Superblock**, the **Inode**, the **Dentry**, and the **File**. Each of these structures contains a pointer to a table of operations function pointers. Each function pointer can be bound at runtime to any function that matches the interface. This allows the kernel to invoke specific functions depending on the concrete file system implementation (like ext4 or xfs).

### Superblock

The `super_block` structure represents one mounted file system instance. It stores metadata about the filesystem itself, such as block size, and the root directory of the mount.

Here is a trimmed version of the `super_block` structure defined in `include/linux/fs.h`:

```C
struct super_block {
	struct list_head	s_list;		/* Keep this first */
	dev_t			s_dev;		/* search index; _not_ kdev_t */
	unsigned long		s_blocksize;
	struct file_system_type	*s_type;
	const struct super_operations	*s_op;
	unsigned long		s_magic;
	struct dentry		*s_root;
    // ...
	struct list_head	s_mounts;	/* list of mounts; _not_ for fs use */
    // ...
	struct list_head	s_inodes;	/* all inodes */
} __randomize_layout;
```

Let's look at some key fields:
*   `s_magic`: Contains a "magic number" that allows the kernel to verify that the disk contains the file system it expects.
*   `s_root`: This points to the `dentry` of the file system's root directory (e.g., the `/` of the mounted partition).
*   `s_inodes`: A list of all inodes belonging to this file system instance.

The most important fields here for abstraction are `s_op` and `s_type`. It points to `struct super_operations`, which defines how the VFS can interact with this specific filesystem instance. `s_type` abstracts the file system type, and once the `s_type` is determined, the file types corresponding to subsequent data structures are also determined. They just need to bind the corresponding operation function pointer table.

```C
struct super_operations {
   	struct inode *(*alloc_inode)(struct super_block *sb);
	void (*destroy_inode)(struct inode *);
   	void (*dirty_inode) (struct inode *, int flags);
	int (*write_inode) (struct inode *, struct writeback_control *wbc);
	int (*drop_inode) (struct inode *);
	void (*put_super) (struct super_block *);
	int (*sync_fs)(struct super_block *sb, int wait);
    // ...
};
```

Since the specific type of the file system is determined by the superblock, the construction, destruction, and other operations on the inode itself are placed in `super_operations` rather than `inode_operations`.

### Inode

The `inode` (index node) represents a specific object within the filesystem, such as a file or a directory. It contains all the metadata about the file **except** its name. This includes permissions, owner, size, and timestamps.

```C
struct inode {
	umode_t			i_mode;
	kuid_t			i_uid;
	kgid_t			i_gid;
	const struct inode_operations	*i_op;
	struct super_block	*i_sb;
	struct address_space	*i_mapping;
	unsigned long		i_ino;
	loff_t			i_size;
    // ...
	struct list_head	i_lru;		/* inode LRU list */
	union {
		struct hlist_head	i_dentry;
		struct rcu_head		i_rcu;
	};
    // ...
	union {
		const struct file_operations	*i_fop;	/* former ->i_op->default_file_ops */
		void (*free_inode)(struct inode *);
	};
} __randomize_layout;
```

*   `i_ino`: **Inode Number**. This is a unique numerical identifier within its filesystem that the kernel uses to identify the `inode`.
*   `i_size`: **File Size**. Represents the size of the file's content in bytes.
*   `i_dentry`: **Directory Entry List Head**. An `inode` can have multiple names (via hard links) and thus can be pointed to by multiple `dentry` structures. This `hlist_head` is the head of a hash list that links all `dentry` objects pointing to this `inode`.
*   `i_lru`: **Least Recently Used List**. The kernel caches active `inodes` in memory to improve performance. The `i_lru` field is used to place this `inode` on an LRU list. When memory pressure is high, the kernel can reclaim `inodes` that have not been used for a long time from the tail of this list.
*   `i_op`: Points to an `inode_operations` structure. It defines operations not on the `inode` metadata itself, but rather **on the filesystem object that the `inode` represents**. For example:
    *   `create`: Create a new file within a directory (which is represented by an inode).
    *   `lookup`: Find a file within a directory.
    *   `mkdir`: Create a new directory.
    *   `rename`: Rename a file or directory.

```C
struct inode_operations {
	struct dentry * (*lookup) (struct inode *,struct dentry *, unsigned int);
	int (*create) (struct mnt_idmap *, struct inode *,struct dentry *,
		       umode_t, bool);
	int (*link) (struct dentry *,struct inode *,struct dentry *);
	int (*unlink) (struct inode *,struct dentry *);
	struct dentry *(*mkdir) (struct mnt_idmap *, struct inode *,
				 struct dentry *, umode_t);
	int (*rename) (struct mnt_idmap *, struct inode *, struct dentry *,
			struct inode *, struct dentry *, unsigned int);
    // ...
} ____cacheline_aligned;
```

### Dentry

You might notice that the `inode` structure does not contain the filename. This is a deliberate design choice in Linux. The mapping between a filename and an inode is handled by the **Dentry** (Directory Entry).

The `dentry` structure connects a specific name (like "home") to a specific inode. It also maintains the directory tree structure by pointing to its parent.

```C
struct dentry {
	struct dentry *d_parent;	/* parent directory */
	struct qstr d_name;
	struct inode *d_inode;		/* Where the name belongs to - NULL is
					 * negative */
	const struct dentry_operations *d_op;
	struct super_block *d_sb;	/* The root of the dentry tree */
	struct hlist_head d_children;	/* our children */
    // ...
};
```

Let's look at the structure of the dentry:
*   `d_inode`: Points to the specific `inode` associated with this filename.
*   `d_parent`: Points to the dentry of the parent directory, allowing us to traverse up the tree.
*   `d_children`: A list of dentries that are children of this directory (subdirectories or files).
*   `d_name`: Contains the actual string of the filename (e.g., "foo.txt").
*   `d_sb`: Points back to the superblock, indicating which filesystem this dentry belongs to.

This separation allows for hard links: **multiple dentries with different names can have their inode pointers point to the same inode.** T
Also, to rename a file, the kernel only needs to modify the **`d_name` member in the** `dentry`, without moving the actual data on the disk or creating a new inode.

## Struct File, File from a Process's View

I plan to discuss the file structure separately in this section.

Perhaps you might ask: *If we already have the inode, why do we need the file structure?*

The distinction is vital because the `inode` describes the file itself, while the `file` structure describes the **interaction of a process with that file**. The `file` structure represents the file from the perspective of a process.

First, let's look at the definition of `struct file`:

```C
struct file {
	struct path			f_path;
	struct inode			*f_inode;
	const struct file_operations	*f_op;
    // ...
	spinlock_t			f_lock;
	atomic_long_t			f_count;
	unsigned int			f_flags;
	fmode_t				f_mode;
	loff_t				f_pos;
} __randomize_layout
```

*   `f_path`: Contains the `dentry` and `vfsmount`, locating the file in the namespace.We'll explain namespace in later chapeters in detail.
*   `f_inode`: Points to the inode associated with this file structure.
*   `f_op`: The table of operations for this open file (read, write, etc.).
*   `f_lock`: A spinlock protecting the file structure's fields.
*   `f_count`: Reference count. The file structure is freed only when this drops to zero.
*   `f_flags`: Flags passed during open (e.g., `O_NONBLOCK`).
*   `f_mode`: The mode in which the file was opened (e.g., `FMODE_READ`, `FMODE_WRITE`).
*   `f_pos`: The current file offset (cursor) for reading or writing.

Multiple file structures whose inode pointers point to the same inode can have completely different values for f_mode and f_pos fields, because different processes can open the same file instance with different read/write modes and different read/write offset positions. In other words, the file structure is an abstraction made by VFS for processes. In contrast, inode, super_block, and dentry structures are closer to the representation of concrete file system instances.

The `f_op` defines how a process interacts with the open file. When a user calls system calls like `read()` or `write()`, the kernel eventually invokes the corresponding function in this structure.

```C
struct file_operations {
	loff_t (*llseek) (struct file *, loff_t, int);
	ssize_t (*read) (struct file *, char __user *, size_t, loff_t *);
	ssize_t (*write) (struct file *, const char __user *, size_t, loff_t *);
	int (*open) (struct inode *, struct file *);
	int (*release) (struct inode *, struct file *);
    // ...
} __randomize_layout;
```

## Conclusion

In this part, we have established the foundation of the Virtual File System. We learned that the VFS uses four main objects—Superblock, Inode, Dentry, and File—to abstract the details of specific file systems, and implements specific operations for different concrete file systems by defining abstract function pointers through operation structures.

In the next part, I will start from the mounting of a file system and gradually introduce how these common data structures and operations are specifically implemented for a concrete file system.

## Links

*   [Linux Kernel Documentation - VFS](https://www.kernel.org/doc/html/latest/filesystems/vfs.html)