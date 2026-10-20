#include <stdlib.h>

/*
 * Unsafe: the new node q has right == NULL, so p is NULL and p->left
 * dereferences nil. The frame Here(q) of the new node is entered from its
 * parent and leaves to it (s->left = q rewinds to s), so the step going up
 * from it must be encoded with the parent as receiver.
 */
struct node {
    int data;
    struct node *left;
    struct node *right;
};

void bst_unsafe_linked_new(struct node *root) {
    struct node *s;
    struct node *q;
    struct node *r;
    struct node *p;
    struct node *x;

    if (root == NULL)
        return;
    s = root->right;
    if (s == NULL)
        return;
    q = malloc(sizeof(struct node));
    s->left = q;
    r = s->left;
    p = r->right;
    x = p->left;
}
