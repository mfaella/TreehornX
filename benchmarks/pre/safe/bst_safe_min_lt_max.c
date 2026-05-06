#include <stdbool.h>
#include <stdlib.h>
struct Node {
    int data;
    struct Node *left;
    struct Node *right;
};

void bst_safe_min_lt_max(struct Node *root) {
    struct Node *tmp;
    struct Node *current;
    int min;
    int max;
    _Bool singleton;
    singleton = true;
    if(!root) {
        return;
    }
    tmp = root->left;
    if(!tmp) {
        min = root->data;
    }
    else {
        singleton = false;
        current = root;
        while(current) {
            tmp = current;
            current = current->left;
        }
        min = tmp->data;
    }
    tmp = root->right;
    if(!tmp) {
        max = root->data;
    }
    else {
        singleton = false;
        current = root;
        while(current) {
            tmp = current;
            current = current->right;
        }
        max = tmp->data;
    }
    if (!singleton) {
        assert(min < max);
    }
}

bool nondet_bool();

int nondet_int();

struct Node* nondet_tree(int depth) {
    if (depth == 0 || nondet_bool())
        return NULL;

    struct Node* n = malloc(sizeof(struct Node));
    n->data = nondet_int();
    n->left = nondet_tree(depth - 1);
    n->right = nondet_tree(depth - 1);
    return n;
}

struct IsBst {
    int min;
    int max;
    int isbst;
};

struct IsBst is_bst_rec(struct Node *root) {
    struct IsBst result;
    result.isbst = false;
    if(root->left != NULL) {
        struct IsBst lr = is_bst_rec(root->left);
        result.min = lr.min;
        result.isbst = lr.max < root->data;
    }
    else {
        result.min = root->data;
        result.isbst = true;
    }

    if(root->right != NULL) {
        struct IsBst rr = is_bst_rec(root->right);
        result.max = rr.max;
        result.isbst = rr.min > root->data && result.isbst;
    }
    else {
        result.max = root->data;
    }

    return result;

}

int isbst(struct Node *root) {
    return is_bst_rec(root).isbst;
}

int main() {
    struct Node *root = nondet_tree(5);
    __CPROVER_assume(is_bst_rec(root).isbst);
    bst_safe_min_lt_max(root);
}
